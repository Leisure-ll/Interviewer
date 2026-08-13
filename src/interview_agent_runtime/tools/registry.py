from __future__ import annotations

import time
import asyncio
import json
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional, Protocol, Union

from interview_agent_runtime.blackboard import InterviewBlackboard
from interview_agent_runtime.errors import (
    ToolDurabilityError,
    ToolExecutionError,
    ToolPermissionError,
    ToolTimeoutError,
)
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


class ToolResourceResolver(Protocol):
    def resource_key(
        self,
        tool: "ToolSpec",
        arguments: dict[str, Any],
    ) -> Optional[str]:
        ...


class DefaultToolResourceResolver:
    """Best-effort local resource identity for conflict detection."""

    def resource_key(
        self,
        tool: "ToolSpec",
        arguments: dict[str, Any],
    ) -> Optional[str]:
        if "path" in arguments:
            return f"file:{arguments['path']}"
        if "candidate_id" in arguments:
            return f"candidate:{arguments['candidate_id']}"
        if "resource_id" in arguments:
            return f"resource:{arguments['resource_id']}"
        return None


class ToolConcurrencyMode(str, Enum):
    SEQUENTIAL = "sequential"
    PARALLEL_SAFE = "parallel_safe"


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


@dataclass
class DurableToolExecutionRecord:
    """Recoverable execution fact, separate from the observability trace."""

    invocation_key: ToolInvocationKey
    tool_name: str
    status: str
    result: Optional["ToolResult"] = None
    result_reference: str = ""
    side_effect: bool = False
    idempotency_key: Optional[str] = None
    completed_at: Optional[datetime] = None
    run_id: Optional[str] = None
    tool_call_id: str = ""


@dataclass
class ToolBatchResult:
    results: List["ToolResult"]
    parallel_tool_batches: int = 0
    max_parallelism: int = 1
    sequential_tool_calls: int = 0
    resource_conflicts: int = 0


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
    parallel_safe: bool = False
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
        resource_resolver: Optional[ToolResourceResolver] = None,
        concurrency_mode: str = ToolConcurrencyMode.PARALLEL_SAFE,
    ) -> None:
        self.registry = registry
        self.policy = policy
        self.resource_version_resolver = resource_version_resolver
        self.resource_resolver = resource_resolver or DefaultToolResourceResolver()
        self.concurrency_mode = concurrency_mode

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
        durable_records: Optional[dict[str, DurableToolExecutionRecord]] = None,
        persist_durable_record: Optional[Callable[[DurableToolExecutionRecord], Awaitable[None]]] = None,
        run_id: Optional[str] = None,
    ) -> "ToolResult":
        tool = None
        resource_version: Optional[str] = None
        invocation_key: Optional[ToolInvocationKey] = None
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
                durable = durable_records.get(invocation_key.fingerprint) if durable_records else None
                if durable is not None and durable.status == "success" and durable.side_effect:
                    recovered = durable.result or ToolResult(
                        tool_call_id=tool_call.id,
                        tool_name=tool_call.name,
                        ok=True,
                        status="durable_recovered",
                    )
                    recovered = ToolResult(
                        tool_call_id=tool_call.id,
                        tool_name=tool_call.name,
                        ok=recovered.ok,
                        value=recovered.value,
                        error=recovered.error,
                        duration_ms=0.0,
                        status="durable_recovered",
                        cache_hit=True,
                    )
                    governance.records[invocation_key] = ToolExecutionRecord(
                        invocation_key=invocation_key,
                        tool_call_id=tool_call.id,
                        status="success",
                        result=recovered,
                        invocation_count=1,
                        first_round=round_no,
                        last_round=round_no,
                    )
                    governance.cache_hits += 1
                    return recovered
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
                key = invocation_key or ToolInvocationKey.from_call(
                    tool.name,
                    tool_call.arguments,
                    resource_version,
                )
                record = governance.records[key]
                record.status = "success"
                record.result = result
                if tool.spec.idempotent and not tool.spec.side_effect:
                    governance.cache[key] = result
                governance._consecutive_duplicate_rejections = 0
                await self._persist_durable_record(
                    durable_records=durable_records,
                    persist_durable_record=persist_durable_record,
                    key=key,
                    tool=tool,
                    result=result,
                    status="success",
                    run_id=run_id,
                )
            return result
        except Exception as exc:
            if isinstance(exc, ToolDurabilityError):
                raise
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
                key = invocation_key or ToolInvocationKey.from_call(
                    tool.name,
                    tool_call.arguments,
                    resource_version,
                )
                record = governance.records[key]
                record.status = result.status
                record.result = result
                governance._consecutive_duplicate_rejections = 0
                await self._persist_durable_record(
                    durable_records=durable_records,
                    persist_durable_record=persist_durable_record,
                    key=key,
                    tool=tool,
                    result=result,
                    status=result.status,
                    run_id=run_id,
                )
            return result

    async def execute_batch(
        self,
        tool_calls: List[ToolCall],
        context: ToolContext,
        visible_tools: set[str],
        *,
        governance: Optional[ToolGovernanceState] = None,
        round_no: int = 0,
        durable_records: Optional[dict[str, DurableToolExecutionRecord]] = None,
        persist_durable_record: Optional[Callable[[DurableToolExecutionRecord], Awaitable[None]]] = None,
        run_id: Optional[str] = None,
    ) -> ToolBatchResult:
        """Execute one assistant batch with deterministic safe parallelism."""
        if not tool_calls:
            return ToolBatchResult(results=[])
        if self.concurrency_mode == ToolConcurrencyMode.SEQUENTIAL:
            results = [
                await self.execute(
                    call,
                    context,
                    visible_tools,
                    governance=governance,
                    round_no=round_no,
                    durable_records=durable_records,
                    persist_durable_record=persist_durable_record,
                    run_id=run_id,
                )
                for call in tool_calls
            ]
            return ToolBatchResult(
                results=results,
                sequential_tool_calls=len(tool_calls),
            )

        results: list[Optional[ToolResult]] = [None] * len(tool_calls)
        seen_keys: set[ToolInvocationKey] = set()
        safe_group: list[tuple[int, ToolCall, Optional[str]]] = []
        parallel_batches = 0
        max_parallelism = 1
        sequential_calls = 0
        resource_conflicts = 0

        async def flush_safe_group() -> None:
            nonlocal parallel_batches, max_parallelism, sequential_calls
            if not safe_group:
                return
            if len(safe_group) == 1:
                index, call, _ = safe_group[0]
                result = await self.execute(
                    call,
                    context,
                    visible_tools,
                    governance=governance,
                    round_no=round_no,
                    durable_records=durable_records,
                    persist_durable_record=persist_durable_record,
                    run_id=run_id,
                )
                result.execution_mode = ToolConcurrencyMode.SEQUENTIAL.value
                result.resource_key = self._resource_key(
                    self.registry.resolve(call.name).spec,
                    call.arguments,
                )
                results[index] = result
                sequential_calls += 1
            else:
                parallel_batches += 1
                max_parallelism = max(max_parallelism, len(safe_group))
                values = await asyncio.gather(
                    *[
                        self.execute(
                            call,
                            context,
                            visible_tools,
                            governance=governance,
                            round_no=round_no,
                            durable_records=durable_records,
                            persist_durable_record=persist_durable_record,
                            run_id=run_id,
                        )
                        for _, call, _ in safe_group
                    ]
                )
                for (index, _, _), value in zip(safe_group, values):
                    value.execution_mode = ToolConcurrencyMode.PARALLEL_SAFE.value
                    value.resource_key = self._resource_key(
                        self.registry.resolve(tool_calls[index].name).spec,
                        tool_calls[index].arguments,
                    )
                    results[index] = value
            safe_group.clear()

        for index, call in enumerate(tool_calls):
            try:
                tool = self.registry.resolve(call.name)
            except KeyError:
                result = await self.execute(
                    call,
                    context,
                    visible_tools,
                    governance=governance,
                    round_no=round_no,
                    durable_records=durable_records,
                    persist_durable_record=persist_durable_record,
                    run_id=run_id,
                )
                result.execution_mode = ToolConcurrencyMode.SEQUENTIAL.value
                result.resource_key = None
                results[index] = result
                sequential_calls += 1
                continue
            key = await self._invocation_key(call)
            if key in seen_keys:
                results[index] = ToolResult(
                    tool_call_id=call.id,
                    tool_name=call.name,
                    ok=False,
                    error="duplicate tool invocation in the same batch rejected",
                    status="duplicate_rejected",
                    duplicate=True,
                )
                continue
            seen_keys.add(key)
            resource_key = self._resource_key(tool.spec, call.arguments)
            can_parallel = (
                tool.spec.parallel_safe
                and self.concurrency_mode == ToolConcurrencyMode.PARALLEL_SAFE
            )
            if not can_parallel:
                await flush_safe_group()
                result = await self.execute(
                    call,
                    context,
                    visible_tools,
                    governance=governance,
                    round_no=round_no,
                    durable_records=durable_records,
                    persist_durable_record=persist_durable_record,
                    run_id=run_id,
                )
                result.execution_mode = ToolConcurrencyMode.SEQUENTIAL.value
                result.resource_key = resource_key
                results[index] = result
                sequential_calls += 1
                continue
            if resource_key is not None and any(
                existing_resource == resource_key
                for _, _, existing_resource in safe_group
            ):
                resource_conflicts += 1
                await flush_safe_group()
                results[index] = await self.execute(
                    call,
                    context,
                    visible_tools,
                    governance=governance,
                    round_no=round_no,
                    durable_records=durable_records,
                    persist_durable_record=persist_durable_record,
                    run_id=run_id,
                )
                results[index].execution_mode = ToolConcurrencyMode.SEQUENTIAL.value
                results[index].resource_key = resource_key
                sequential_calls += 1
                continue
            safe_group.append((index, call, resource_key))

        await flush_safe_group()
        ordered_results = [
            item
            if item is not None
            else ToolResult(
                tool_call_id=call.id,
                tool_name=call.name,
                ok=False,
                error="tool execution did not produce a result",
                status="error",
            )
            for item, call in zip(results, tool_calls)
        ]
        return ToolBatchResult(
            results=ordered_results,
            parallel_tool_batches=parallel_batches,
            max_parallelism=max_parallelism,
            sequential_tool_calls=sequential_calls,
            resource_conflicts=resource_conflicts,
        )

    async def _invocation_key(self, tool_call: ToolCall) -> ToolInvocationKey:
        resource_version: Optional[str] = None
        tool = self.registry.resolve(tool_call.name)
        if self.resource_version_resolver is not None:
            resource_version = await self.resource_version_resolver.version_for(
                tool.spec,
                tool_call.arguments,
            )
        return ToolInvocationKey.from_call(
            tool_call.name,
            tool_call.arguments,
            resource_version,
        )

    def _resource_key(self, tool: ToolSpec, arguments: dict[str, Any]) -> Optional[str]:
        if self.resource_resolver is None:
            return None
        return self.resource_resolver.resource_key(tool, arguments)

    async def _persist_durable_record(
        self,
        *,
        durable_records: Optional[dict[str, DurableToolExecutionRecord]],
        persist_durable_record: Optional[Callable[[DurableToolExecutionRecord], Awaitable[None]]],
        key: ToolInvocationKey,
        tool: Tool,
        result: "ToolResult",
        status: str,
        run_id: Optional[str],
    ) -> None:
        if durable_records is None:
            return
        if not tool.spec.side_effect:
            return
        record = DurableToolExecutionRecord(
            invocation_key=key,
            tool_name=tool.name,
            status=status,
            result=result,
            result_reference=hashlib.sha256(
                json.dumps(result.value, ensure_ascii=False, default=str).encode("utf-8")
            ).hexdigest()[:16],
            side_effect=tool.spec.side_effect,
            idempotency_key=f"idem_{hashlib.sha256(key.fingerprint.encode('utf-8')).hexdigest()[:20]}",
            completed_at=datetime.now(timezone.utc) if status == "success" else None,
            run_id=run_id,
            tool_call_id=result.tool_call_id,
        )
        durable_records[key.fingerprint] = record
        if persist_durable_record is not None:
            try:
                await persist_durable_record(record)
            except Exception as exc:
                raise ToolDurabilityError(
                    f"Durable tool record could not be persisted: {tool.name}"
                ) from exc


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
    execution_mode: str = ToolConcurrencyMode.SEQUENTIAL.value
    resource_key: Optional[str] = None


class ToolResultContextProjector:
    """Bounds tool output inserted into the next LLM request."""

    def __init__(self, max_chars: int = 4000) -> None:
        self.max_chars = max(256, max_chars)

    def project(self, value: Any) -> Any:
        encoded = json.dumps(value, ensure_ascii=False, default=str)
        if len(encoded) <= self.max_chars:
            return value
        preview = encoded[: self.max_chars]
        return {
            "preview": preview,
            "truncated": True,
            "original_size": len(encoded),
            "content_hash": hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16],
        }


