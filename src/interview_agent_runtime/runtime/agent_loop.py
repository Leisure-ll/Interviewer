from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any, Optional
from uuid import uuid4

from interview_agent_runtime.blackboard import InterviewBlackboard
from interview_agent_runtime.execution import ExecutionStrategy, StopReason
from interview_agent_runtime.memory import MemoryCompressor, SessionMemory
from interview_agent_runtime.memory import MemoryContextBuilder, MemoryScope
from interview_agent_runtime.messages import AgentMessage
from interview_agent_runtime.providers import LLMProvider, LLMRequest, LLMResponse
from interview_agent_runtime.runtime.events import TraceContext
from interview_agent_runtime.runtime.events import InMemoryEventBus, RuntimeEvent, RuntimeEventType
from interview_agent_runtime.tools import ToolContext, ToolExecutor, ToolGovernanceState


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
    execution_strategy: ExecutionStrategy = ExecutionStrategy.REACT
    max_duplicate_calls: int = 1


@dataclass
class AgentRunResult:
    final_message: AgentMessage
    messages: list[AgentMessage]
    rounds: int
    tool_calls: int
    stop_reason: str
    parsed: Optional[dict[str, Any]] = None
    responses: list[LLMResponse] = field(default_factory=list)
    execution_strategy: ExecutionStrategy = ExecutionStrategy.REACT
    unique_tool_calls: int = 0
    cache_hits: int = 0
    duplicate_calls: int = 0
    duration_ms: float = 0.0
    total_tokens: int = 0
    requested_tool_calls: int = 0
    executed_tool_calls: int = 0


class AgentLoop:
    """K-inspired ReAct loop for one specialist agent invocation.

    It owns LLM/tool messages only. Domain state remains the Runtime's Blackboard.
    Tool governance state is deliberately scoped to this run.
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
        self.memory_context_builder = MemoryContextBuilder(memory, compressor=compressor)

    async def run(self, request: AgentRunRequest) -> AgentRunResult:
        loop_trace = self._child_trace(request, kind="loop")
        scope = request.memory_scope or MemoryScope(request.session_id, request.agent_name)
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
            metadata={
                "max_rounds": request.max_rounds,
                "max_tool_calls": request.max_tool_calls,
                "execution_strategy": request.execution_strategy.value,
            },
            trace=loop_trace,
        )

        responses: list[LLMResponse] = []
        rounds = 0
        tool_calls = 0
        requested_tool_calls = 0
        executed_tool_calls = 0
        total_tokens = 0
        last_message = AgentMessage.assistant("")
        started = time.perf_counter()
        governance = ToolGovernanceState(request.max_duplicate_calls)

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
                        StopReason.TOOL_BUDGET_EXCEEDED.value,
                        responses,
                        governance=governance,
                        requested_tool_calls=requested_tool_calls,
                        executed_tool_calls=executed_tool_calls,
                        total_tokens=total_tokens,
                        started=started,
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
                        StopReason.TOKEN_BUDGET_EXCEEDED.value,
                        responses,
                        governance=governance,
                        requested_tool_calls=requested_tool_calls,
                        executed_tool_calls=executed_tool_calls,
                        total_tokens=total_tokens,
                        started=started,
                        trace=loop_trace,
                    )

                if not last_message.tool_calls:
                    return await self._completed(
                        request,
                        messages,
                        last_message,
                        rounds,
                        tool_calls,
                        responses,
                        governance,
                        requested_tool_calls,
                        executed_tool_calls,
                        total_tokens,
                        started,
                        loop_trace,
                    )

                requested_tool_calls += len(last_message.tool_calls)
                remaining_budget = request.max_tool_calls - tool_calls
                if len(last_message.tool_calls) > remaining_budget:
                    await self._append_batch_rejection(
                        request,
                        messages,
                        memory_key,
                        last_message.tool_calls,
                        remaining_budget,
                        round_no,
                        trace=loop_trace,
                    )
                    tool_calls = max(0, remaining_budget)
                    return await self._stopped(
                        request,
                        messages,
                        last_message,
                        rounds,
                        tool_calls,
                        StopReason.TOOL_BUDGET_EXCEEDED.value,
                        responses,
                        governance=governance,
                        requested_tool_calls=requested_tool_calls,
                        executed_tool_calls=executed_tool_calls,
                        total_tokens=total_tokens,
                        started=started,
                        trace=loop_trace,
                    )

                for tool_call in last_message.tool_calls:
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
                        governance=governance,
                        round_no=round_no,
                    )
                    executed_tool_calls += 1
                    if result.ok:
                        content = json.dumps(result.value, ensure_ascii=False)
                        event_type = RuntimeEventType.TOOL_SUCCEEDED
                    else:
                        content = json.dumps(
                            {"ok": False, "error": result.error, "status": result.status},
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
                            "status": result.status,
                            "cache_hit": result.cache_hit,
                            "duplicate": result.duplicate,
                        },
                        trace=tool_span,
                    )
                    if governance.repeated_tool_call:
                        return await self._stopped(
                            request,
                            messages,
                            last_message,
                            rounds,
                            tool_calls,
                            StopReason.REPEATED_TOOL_CALL.value,
                            responses,
                            governance=governance,
                            requested_tool_calls=requested_tool_calls,
                            executed_tool_calls=executed_tool_calls,
                            total_tokens=total_tokens,
                            started=started,
                            trace=loop_trace,
                        )

            return await self._stopped(
                request,
                messages,
                last_message,
                rounds,
                tool_calls,
                StopReason.MAX_ROUNDS.value,
                responses,
                governance=governance,
                requested_tool_calls=requested_tool_calls,
                executed_tool_calls=executed_tool_calls,
                total_tokens=total_tokens,
                started=started,
                trace=loop_trace,
            )
        except asyncio.TimeoutError:
            return await self._stopped(
                request,
                messages,
                last_message,
                rounds,
                tool_calls,
                StopReason.TIMEOUT.value,
                responses,
                governance=governance,
                requested_tool_calls=requested_tool_calls,
                executed_tool_calls=executed_tool_calls,
                total_tokens=total_tokens,
                started=started,
                trace=loop_trace,
            )
        except Exception as exc:
            return await self._stopped(
                request,
                messages,
                last_message,
                rounds,
                tool_calls,
                StopReason.PROVIDER_ERROR.value,
                responses,
                error_type=type(exc).__name__,
                governance=governance,
                requested_tool_calls=requested_tool_calls,
                executed_tool_calls=executed_tool_calls,
                total_tokens=total_tokens,
                started=started,
                trace=loop_trace,
            )

    async def _completed(
        self,
        request: AgentRunRequest,
        messages: list[AgentMessage],
        last_message: AgentMessage,
        rounds: int,
        tool_calls: int,
        responses: list[LLMResponse],
        governance: ToolGovernanceState,
        requested_tool_calls: int,
        executed_tool_calls: int,
        total_tokens: int,
        started: float,
        trace: Optional[TraceContext],
    ) -> AgentRunResult:
        duration_ms = (time.perf_counter() - started) * 1000
        await self._emit(
            RuntimeEventType.AGENT_LOOP_FINISHED,
            request,
            metadata={
                "rounds": rounds,
                "tool_calls": tool_calls,
                "stop_reason": StopReason.COMPLETED.value,
                "duration_ms": duration_ms,
                "execution_strategy": request.execution_strategy.value,
                "unique_tool_calls": governance.unique_tool_calls,
                "cache_hits": governance.cache_hits,
                "duplicate_calls": governance.duplicate_calls,
            },
            trace=trace,
        )
        return AgentRunResult(
            final_message=last_message,
            messages=messages,
            rounds=rounds,
            tool_calls=tool_calls,
            stop_reason=StopReason.COMPLETED.value,
            parsed=_parse_json_object(last_message.content),
            responses=responses,
            execution_strategy=request.execution_strategy,
            unique_tool_calls=governance.unique_tool_calls,
            cache_hits=governance.cache_hits,
            duplicate_calls=governance.duplicate_calls,
            duration_ms=duration_ms,
            total_tokens=total_tokens,
            requested_tool_calls=requested_tool_calls,
            executed_tool_calls=executed_tool_calls,
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
        governance: Optional[ToolGovernanceState] = None,
        requested_tool_calls: int = 0,
        executed_tool_calls: int = 0,
        total_tokens: int = 0,
        started: Optional[float] = None,
        trace: Optional[TraceContext] = None,
    ) -> AgentRunResult:
        duration_ms = (time.perf_counter() - started) * 1000 if started else 0.0
        await self._emit(
            RuntimeEventType.AGENT_LOOP_STOPPED,
            request,
            metadata={
                "rounds": rounds,
                "tool_calls": tool_calls,
                "stop_reason": reason,
                "execution_strategy": request.execution_strategy.value,
                "unique_tool_calls": governance.unique_tool_calls if governance else 0,
                "cache_hits": governance.cache_hits if governance else 0,
                "duplicate_calls": governance.duplicate_calls if governance else 0,
                "duration_ms": duration_ms,
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
            execution_strategy=request.execution_strategy,
            unique_tool_calls=governance.unique_tool_calls if governance else 0,
            cache_hits=governance.cache_hits if governance else 0,
            duplicate_calls=governance.duplicate_calls if governance else 0,
            duration_ms=duration_ms,
            total_tokens=total_tokens,
            requested_tool_calls=requested_tool_calls,
            executed_tool_calls=executed_tool_calls,
        )

    async def _append_batch_rejection(
        self,
        request: AgentRunRequest,
        messages: list[AgentMessage],
        memory_key: str,
        tool_calls: list[Any],
        remaining_budget: int,
        round_no: int,
        *,
        trace: Optional[TraceContext],
    ) -> None:
        feedback = {
            "ok": False,
            "error": "tool call batch rejected",
            "requested_tool_calls": len(tool_calls),
            "remaining_tool_budget": max(0, remaining_budget),
        }
        for tool_call in tool_calls:
            tool_message = AgentMessage.tool(
                tool_call_id=tool_call.id,
                name=tool_call.name,
                content=json.dumps(feedback, ensure_ascii=False),
            )
            messages.append(tool_message)
            await self.memory.append(memory_key, tool_message)
            await self._emit(
                RuntimeEventType.TOOL_FAILED,
                request,
                metadata={
                    "round": round_no,
                    "tool": tool_call.name,
                    "status": "batch_rejected",
                    "requested_tool_calls": len(tool_calls),
                    "remaining_tool_budget": max(0, remaining_budget),
                },
                trace=trace,
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
