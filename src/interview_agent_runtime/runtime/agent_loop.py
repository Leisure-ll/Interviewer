from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any, Optional
from uuid import uuid4

from interview_agent_runtime.blackboard import InterviewBlackboard
from interview_agent_runtime.memory import MemoryCompressor, SessionMemory
from interview_agent_runtime.memory import MemoryContextBuilder, MemoryScope
from interview_agent_runtime.messages import AgentMessage
from interview_agent_runtime.providers import LLMProvider, LLMRequest, LLMResponse
from interview_agent_runtime.runtime.events import TraceContext
from interview_agent_runtime.runtime.events import InMemoryEventBus, RuntimeEvent, RuntimeEventType
from interview_agent_runtime.tools import ToolContext, ToolExecutor


@dataclass
class AgentRunRequest:
    session_id: str
    agent_name: str
    skill_name: str
    initial_messages: list[AgentMessage]
    visible_tools: set[str]
    tool_executor: ToolExecutor
    tool_context: ToolContext
    response_schema: Optional[str] = None
    max_rounds: int = 4
    max_tool_calls: int = 8
    token_budget: int = 2000
    timeout_seconds: float = 15.0
    memory_key: Optional[str] = None
    memory_scope: Optional[MemoryScope] = None
    blackboard: Optional[InterviewBlackboard] = None
    memory_limit: Optional[int] = None
    include_interaction_memory: bool = True
    include_domain_snapshot: bool = True
    trace: Optional[TraceContext] = None


@dataclass
class AgentRunResult:
    final_message: AgentMessage
    messages: list[AgentMessage]
    rounds: int
    tool_calls: int
    stop_reason: str
    parsed: Optional[dict[str, Any]] = None
    responses: list[LLMResponse] = field(default_factory=list)


class AgentLoop:
    """K-inspired ReAct loop for one specialist agent invocation.

    It owns LLM/tool messages only. Domain state remains the Runtime's Blackboard.
    """

    def __init__(
        self,
        llm_provider: LLMProvider,
        memory: SessionMemory,
        event_bus: Optional[InMemoryEventBus] = None,
        compressor: Optional[MemoryCompressor] = None,
    ) -> None:
        self.llm_provider = llm_provider
        self.memory = memory
        self.event_bus = event_bus
        self.compressor = compressor
        self.memory_context_builder = MemoryContextBuilder(
            memory,
            compressor=compressor,
        )

    async def run(self, request: AgentRunRequest) -> AgentRunResult:
        loop_trace = self._child_trace(request, kind="loop")
        scope = request.memory_scope or MemoryScope(
            request.session_id,
            request.agent_name,
        )
        memory_key = request.memory_key or scope.key()
        if request.include_interaction_memory:
            memory_context = await self.memory_context_builder.build(
                scope,
                blackboard=request.blackboard if request.include_domain_snapshot else None,
                max_recent_messages=request.memory_limit or 12,
            )
        else:
            memory_context = await self.memory_context_builder.build(
                scope,
                blackboard=request.blackboard if request.include_domain_snapshot else None,
                max_recent_messages=0,
            )
            memory_context.summary = None
            memory_context.recent_messages = []
        messages = memory_context.to_messages()
        messages.extend(request.initial_messages)
        await self.memory.extend(memory_key, request.initial_messages)

        await self._emit(
            RuntimeEventType.AGENT_LOOP_STARTED,
            request,
            metadata={"max_rounds": request.max_rounds},
            trace=loop_trace,
        )

        responses: list[LLMResponse] = []
        rounds = 0
        tool_calls = 0
        total_tokens = 0
        last_message = AgentMessage.assistant("")
        started = time.perf_counter()

        try:
            for round_no in range(1, request.max_rounds + 1):
                rounds = round_no
                if tool_calls >= request.max_tool_calls:
                    return await self._stopped(
                        request,
                        messages,
                        last_message,
                        rounds,
                        tool_calls,
                        "tool_budget_exceeded",
                        responses,
                        trace=loop_trace,
                    )

                llm_request = LLMRequest(
                    messages=list(messages),
                    tools=request.tool_executor.registry.specs(request.visible_tools),
                    response_schema=request.response_schema,
                    max_tokens=request.token_budget,
                    timeout=request.timeout_seconds,
                )
                llm_span = self._child_trace(request, kind="llm", parent=loop_trace)
                await self._emit(
                    RuntimeEventType.LLM_REQUESTED,
                    request,
                    metadata={"round": round_no, "tool_count": len(llm_request.tools)},
                    trace=llm_span,
                )
                response = await asyncio.wait_for(
                    self.llm_provider.chat(llm_request),
                    timeout=request.timeout_seconds,
                )
                responses.append(response)
                last_message = response.message
                messages.append(last_message)
                await self.memory.append(memory_key, last_message)
                total_tokens += response.total_tokens
                await self._emit(
                    RuntimeEventType.LLM_RESPONDED,
                    request,
                    metadata={
                        "round": round_no,
                        "finish_reason": response.finish_reason,
                        "total_tokens": response.total_tokens,
                    },
                    trace=llm_span,
                )

                if total_tokens > request.token_budget:
                    return await self._stopped(
                        request,
                        messages,
                        last_message,
                        rounds,
                        tool_calls,
                        "token_budget_exceeded",
                        responses,
                        trace=loop_trace,
                    )

                if not last_message.tool_calls:
                    parsed = _parse_json_object(last_message.content)
                    await self._emit(
                        RuntimeEventType.AGENT_LOOP_FINISHED,
                        request,
                        metadata={
                            "rounds": rounds,
                            "tool_calls": tool_calls,
                            "stop_reason": "completed",
                            "duration_ms": (time.perf_counter() - started) * 1000,
                        },
                        trace=loop_trace,
                    )
                    return AgentRunResult(
                        final_message=last_message,
                        messages=messages,
                        rounds=rounds,
                        tool_calls=tool_calls,
                        stop_reason="completed",
                        parsed=parsed,
                        responses=responses,
                    )

                for tool_call in last_message.tool_calls:
                    if tool_calls >= request.max_tool_calls:
                        return await self._stopped(
                            request,
                            messages,
                            last_message,
                            rounds,
                            tool_calls,
                            "tool_budget_exceeded",
                            responses,
                            trace=loop_trace,
                        )
                    tool_calls += 1
                    tool_span = self._child_trace(request, kind="tool", parent=loop_trace)
                    await self._emit(
                        RuntimeEventType.TOOL_CALLED,
                        request,
                        metadata={"round": round_no, "tool": tool_call.name},
                        trace=tool_span,
                    )
                    result = await request.tool_executor.execute(
                        tool_call,
                        request.tool_context,
                        request.visible_tools,
                    )
                    if result.ok:
                        content = json.dumps(result.value, ensure_ascii=False)
                        event_type = RuntimeEventType.TOOL_SUCCEEDED
                    else:
                        content = json.dumps(
                            {"ok": False, "error": result.error},
                            ensure_ascii=False,
                        )
                        event_type = RuntimeEventType.TOOL_FAILED
                    tool_message = AgentMessage.tool(
                        tool_call_id=tool_call.id,
                        name=tool_call.name,
                        content=content,
                    )
                    messages.append(tool_message)
                    await self.memory.append(memory_key, tool_message)
                    await self._emit(
                        event_type,
                        request,
                        metadata={
                            "round": round_no,
                            "tool": tool_call.name,
                            "ok": result.ok,
                            "duration_ms": result.duration_ms,
                        },
                        trace=tool_span,
                    )

            return await self._stopped(
                request,
                messages,
                last_message,
                rounds,
                tool_calls,
                "max_rounds",
                responses,
                trace=loop_trace,
            )
        except asyncio.TimeoutError:
            return await self._stopped(
                request,
                messages,
                last_message,
                rounds,
                tool_calls,
                "timeout",
                responses,
                trace=loop_trace,
            )
        except Exception as exc:
            return await self._stopped(
                request,
                messages,
                last_message,
                rounds,
                tool_calls,
                "provider_error",
                responses,
                error_type=type(exc).__name__,
                trace=loop_trace,
            )

    async def _stopped(
        self,
        request: AgentRunRequest,
        messages: list[AgentMessage],
        last_message: AgentMessage,
        rounds: int,
        tool_calls: int,
        reason: str,
        responses: list[LLMResponse],
        error_type: Optional[str] = None,
        trace: Optional[TraceContext] = None,
    ) -> AgentRunResult:
        await self._emit(
            RuntimeEventType.AGENT_LOOP_STOPPED,
            request,
            metadata={
                "rounds": rounds,
                "tool_calls": tool_calls,
                "stop_reason": reason,
                **({"error_type": error_type} if error_type else {}),
            },
            trace=trace,
        )
        return AgentRunResult(
            final_message=last_message,
            messages=messages,
            rounds=rounds,
            tool_calls=tool_calls,
            stop_reason=reason,
            parsed=_parse_json_object(last_message.content),
            responses=responses,
        )

    async def _emit(
        self,
        event_type: RuntimeEventType,
        request: AgentRunRequest,
        metadata: Optional[dict[str, Any]] = None,
        trace: Optional[TraceContext] = None,
    ) -> None:
        if self.event_bus is None:
            return
        await self.event_bus.emit(
            RuntimeEvent(
                event_type,
                request.session_id,
                metadata={
                    "agent": request.agent_name,
                    "skill": request.skill_name,
                    **(metadata or {}),
                },
                trace=trace or request.trace,
            )
        )

    def _child_trace(
        self,
        request: AgentRunRequest,
        *,
        kind: str,
        parent: Optional[TraceContext] = None,
    ) -> Optional[TraceContext]:
        base = parent or request.trace
        if base is None:
            return None
        return TraceContext(
            trace_id=base.trace_id,
            run_id=base.run_id,
            span_id=f"{kind}_{uuid4().hex[:12]}",
            parent_span_id=base.span_id,
        )


def _parse_json_object(content: Optional[str]) -> Optional[dict[str, Any]]:
    if not content:
        return None
    try:
        value = json.loads(content)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None
