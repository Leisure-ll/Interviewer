from __future__ import annotations

import time
import asyncio
import json
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, Optional, Protocol, Union

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


class ResourceVersionResolver(Protocol):
    async def version_for(
        self,
        tool: "ToolSpec",
        arguments: dict[str, Any],
    ) -> Optional[str]:
        ...


@dataclass(frozen=True)
class ToolInvocationKey:
    """Logical invocation identity, separate from the protocol ToolCall.id."""

    tool_name: str
    normalized_arguments: str
    resource_version: Optional[str] = None

    @property
    def fingerprint(self) -> str:
        version = self.resource_version or "-"
        return f"{self.tool_name}:{self.normalized_arguments}:{version}"

    @classmethod
    def from_call(
        cls,
        tool_name: str,
        arguments: dict[str, Any],
        resource_version: Optional[str] = None,
    ) -> "ToolInvocationKey":
        return cls(
            tool_name=tool_name,
            normalized_arguments=json.dumps(
                arguments,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
            resource_version=resource_version,
        )


@dataclass
class ToolExecutionRecord:
    invocation_key: ToolInvocationKey
    tool_call_id: str
    status: str
    result: Optional["ToolResult"] = None
    invocation_count: int = 0
    first_round: int = 0
    last_round: int = 0


class ToolGovernanceState:
    """Run-local state for cache, duplicate, retry, and idempotency decisions."""

    def __init__(self, max_duplicate_calls: int = 1) -> None:
        self.max_duplicate_calls = max(0, max_duplicate_calls)
        self.records: dict[ToolInvocationKey, ToolExecutionRecord] = {}
        self.cache: dict[ToolInvocationKey, ToolResult] = {}
        self.cache_hits = 0
        self.duplicate_calls = 0
        self._consecutive_duplicate_rejections = 0

    @property
    def unique_tool_calls(self) -> int:
        return len(self.records)

    @property
    def repeated_tool_call(self) -> bool:
        return self._consecutive_duplicate_rejections >= 2


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
    source: str = "local"

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
    def __init__(
        self,
        registry: ToolRegistry,
        policy: ToolPolicy,
        resource_version_resolver: Optional[ResourceVersionResolver] = None,
    ) -> None:
        self.registry = registry
        self.policy = policy
        self.resource_version_resolver = resource_version_resolver

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
        *,
        governance: Optional[ToolGovernanceState] = None,
        round_no: int = 0,
    ) -> "ToolResult":
        tool = None
        resource_version: Optional[str] = None
        if governance is not None:
            try:
                tool = self.registry.resolve(tool_call.name)
                if self.resource_version_resolver is not None:
                    resource_version = await self.resource_version_resolver.version_for(
                        tool.spec,
                        tool_call.arguments,
                    )
                invocation_key = ToolInvocationKey.from_call(
                    tool_call.name,
                    tool_call.arguments,
                    resource_version,
                )
                prior = governance.records.get(invocation_key)
                if prior is not None:
                    prior.invocation_count += 1
                    prior.last_round = round_no
                    if prior.result is not None and prior.result.ok:
                        if tool.spec.side_effect:
                            governance.duplicate_calls += 1
                            governance._consecutive_duplicate_rejections += 1
                            return ToolResult(
                                tool_call_id=tool_call.id,
                                tool_name=tool_call.name,
                                ok=False,
                                error="duplicate side-effect invocation rejected",
                                status="duplicate_rejected",
                                duplicate=True,
                            )
                        if not tool.spec.idempotent:
                            governance.duplicate_calls += 1
                            governance._consecutive_duplicate_rejections += 1
                            return ToolResult(
                                tool_call_id=tool_call.id,
                                tool_name=tool_call.name,
                                ok=False,
                                error="duplicate non-idempotent invocation rejected",
                                status="duplicate_rejected",
                                duplicate=True,
                            )
                        if prior.invocation_count <= governance.max_duplicate_calls + 1:
                            cached = governance.cache.get(invocation_key, prior.result)
                            governance.cache_hits += 1
                            governance._consecutive_duplicate_rejections = 0
                            return ToolResult(
                                tool_call_id=tool_call.id,
                                tool_name=tool_call.name,
                                ok=cached.ok,
                                value=cached.value,
                                error=cached.error,
                                status="cache_hit",
                                cache_hit=True,
                            )
                        governance.duplicate_calls += 1
                        governance._consecutive_duplicate_rejections += 1
                        return ToolResult(
                            tool_call_id=tool_call.id,
                            tool_name=tool_call.name,
                            ok=False,
                            error="duplicate tool invocation rejected; use the existing result",
                            status="duplicate_rejected",
                            duplicate=True,
                        )
                    if prior.result is not None and prior.result.status == "retryable_error":
                        governance._consecutive_duplicate_rejections = 0
                    else:
                        governance.duplicate_calls += 1
                        governance._consecutive_duplicate_rejections += 1
                        return ToolResult(
                            tool_call_id=tool_call.id,
                            tool_name=tool_call.name,
                            ok=False,
                            error="duplicate failed invocation rejected",
                            status="duplicate_rejected",
                            duplicate=True,
                        )
                else:
                    governance.records[invocation_key] = ToolExecutionRecord(
                        invocation_key=invocation_key,
                        tool_call_id=tool_call.id,
                        status="pending",
                        invocation_count=1,
                        first_round=round_no,
                        last_round=round_no,
                    )
            except KeyError:
                tool = None

        started = time.perf_counter()
        try:
            value = await self.call(
                tool_call.name,
                tool_call.arguments,
                context,
                visible_tools,
            )
            result = ToolResult(
                tool_call_id=tool_call.id,
                tool_name=tool_call.name,
                ok=True,
                value=value,
                duration_ms=(time.perf_counter() - started) * 1000,
                status="success",
            )
            if governance is not None and tool is not None:
                key = ToolInvocationKey.from_call(tool.name, tool_call.arguments, resource_version)
                record = governance.records[key]
                record.status = "success"
                record.result = result
                if tool.spec.idempotent and not tool.spec.side_effect:
                    governance.cache[key] = result
                governance._consecutive_duplicate_rejections = 0
            return result
        except Exception as exc:
            retryable = isinstance(exc, ToolTimeoutError) or isinstance(
                getattr(exc, "__cause__", None),
                (TimeoutError, asyncio.TimeoutError),
            )
            result = ToolResult(
                tool_call_id=tool_call.id,
                tool_name=tool_call.name,
                ok=False,
                error=str(exc),
                duration_ms=(time.perf_counter() - started) * 1000,
                status="retryable_error" if retryable else "error",
                retryable=retryable,
            )
            if governance is not None and tool is not None:
                key = ToolInvocationKey.from_call(tool.name, tool_call.arguments, resource_version)
                record = governance.records[key]
                record.status = result.status
                record.result = result
                governance._consecutive_duplicate_rejections = 0
            return result


@dataclass
class ToolResult:
    tool_call_id: str
    tool_name: str
    ok: bool
    value: Any = None
    error: Optional[str] = None
    duration_ms: float = 0.0
    status: str = "success"
    cache_hit: bool = False
    duplicate: bool = False
    retryable: bool = False


