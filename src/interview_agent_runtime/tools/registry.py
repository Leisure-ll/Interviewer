from __future__ import annotations

import time
import asyncio
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, Optional, Union

from interview_agent_runtime.blackboard import InterviewBlackboard
from interview_agent_runtime.errors import ToolExecutionError, ToolPermissionError, ToolTimeoutError
from interview_agent_runtime.messages import ToolCall
from interview_agent_runtime.skills import SkillDefinition


@dataclass
class ToolContext:
    session_id: str
    agent_name: str
    skill_name: str
    blackboard: InterviewBlackboard


ToolHandler = Callable[[ToolContext, Dict[str, Any]], Awaitable[Dict[str, Any]]]


@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any] = field(
        default_factory=lambda: {"type": "object", "properties": {}}
    )
    output_schema: Optional[dict[str, Any]] = None
    timeout_seconds: Optional[float] = None
    side_effect: bool = False
    idempotent: bool = True

    def to_provider_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }


@dataclass(init=False)
class Tool:
    spec: ToolSpec
    handler: ToolHandler
    metadata: dict[str, Any] = field(default_factory=dict)

    def __init__(
        self,
        name: Union[str, ToolSpec, None] = None,
        description: Union[str, ToolHandler] = "",
        handler: Optional[ToolHandler] = None,
        metadata: Optional[dict[str, Any]] = None,
        *,
        spec: Optional[ToolSpec] = None,
    ) -> None:
        if spec is None and isinstance(name, ToolSpec):
            spec = name
            if callable(description) and handler is None:
                handler = description
        if spec is None:
            if not isinstance(name, str):
                raise TypeError("Tool requires a name or ToolSpec")
            if not callable(handler):
                raise TypeError("Tool requires an async handler")
            spec = ToolSpec(name=name, description=str(description))
        if not callable(handler):
            raise TypeError("Tool requires an async handler")
        self.spec = spec
        self.handler = handler
        self.metadata = metadata or {}

    @property
    def name(self) -> str:
        return self.spec.name

    @property
    def description(self) -> str:
        return self.spec.description


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def resolve(self, name: str) -> Tool:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise KeyError(f"Tool not registered: {name}") from exc

    def names(self) -> set[str]:
        return set(self._tools)

    def specs(self, names: set[str]) -> list[ToolSpec]:
        return [self.resolve(name).spec for name in sorted(names)]


class ToolPolicy:
    def __init__(self, agent_allowed_tools: Optional[dict[str, set[str]]] = None) -> None:
        self.agent_allowed_tools = agent_allowed_tools or {
            "ProfileAgent": {"resume.retrieve", "jd.retrieve"},
            "PlannerAgent": {"jd.retrieve", "rubric.retrieve"},
            "QuestionAgent": {"resume.retrieve", "jd.retrieve", "question_bank.search", "knowledge.retrieve"},
            "EvaluatorAgent": {"rubric.retrieve", "knowledge.retrieve", "answer.semantic_match"},
            "FollowUpAgent": {"rubric.retrieve", "knowledge.retrieve"},
            "ReportAgent": {"evaluation.history", "evidence.aggregate"},
        }

    def authorize(
        self,
        agent_name: str,
        skill: SkillDefinition,
        session_allowed_tools: Optional[set[str]] = None,
    ) -> set[str]:
        allowed = set(self.agent_allowed_tools.get(agent_name, set()))
        declared = set(skill.allowed_tools)
        session = session_allowed_tools if session_allowed_tools is not None else allowed | declared
        return allowed & declared & session


class ToolExecutor:
    def __init__(self, registry: ToolRegistry, policy: ToolPolicy) -> None:
        self.registry = registry
        self.policy = policy

    async def call(
        self,
        tool_name: str,
        args: dict[str, Any],
        context: ToolContext,
        visible_tools: set[str],
    ) -> dict[str, Any]:
        if tool_name not in visible_tools:
            raise ToolPermissionError(
                f"Tool not authorized for {context.agent_name}: {tool_name}"
            )
        tool = self.registry.resolve(tool_name)
        try:
            if tool.spec.timeout_seconds is None:
                return await tool.handler(context, args)
            return await asyncio.wait_for(
                tool.handler(context, args),
                timeout=tool.spec.timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            raise ToolTimeoutError(f"Tool timed out: {tool_name}") from exc
        except Exception as exc:
            raise ToolExecutionError(f"Tool execution failed: {tool_name}") from exc

    async def execute(
        self,
        tool_call: ToolCall,
        context: ToolContext,
        visible_tools: set[str],
    ) -> "ToolResult":
        started = time.perf_counter()
        try:
            value = await self.call(
                tool_call.name,
                tool_call.arguments,
                context,
                visible_tools,
            )
            return ToolResult(
                tool_call_id=tool_call.id,
                tool_name=tool_call.name,
                ok=True,
                value=value,
                duration_ms=(time.perf_counter() - started) * 1000,
            )
        except Exception as exc:
            return ToolResult(
                tool_call_id=tool_call.id,
                tool_name=tool_call.name,
                ok=False,
                error=str(exc),
                duration_ms=(time.perf_counter() - started) * 1000,
            )


@dataclass
class ToolResult:
    tool_call_id: str
    tool_name: str
    ok: bool
    value: Any = None
    error: Optional[str] = None
    duration_ms: float = 0.0


