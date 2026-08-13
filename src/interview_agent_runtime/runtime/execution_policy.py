from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Generic, Optional, TypeVar

T = TypeVar("T")


@dataclass
class ExecutionPolicy:
    timeout_seconds: float = 15.0
    retry: int = 0
    fallback: Optional[Callable[[], Awaitable[T]]] = None
    name: str = "default"
    max_iterations: int = 4
    max_tool_calls: int = 8
    max_duplicate_calls: int = 1


@dataclass
class ExecutionResult(Generic[T]):
    ok: bool
    value: Optional[T] = None
    error: Optional[Exception] = None
    attempts: int = 0
    used_fallback: bool = False
    trace: list[str] = field(default_factory=list)


class TaskExecutor:
    async def execute(
        self,
        func: Callable[[], Awaitable[T]],
        policy: ExecutionPolicy,
    ) -> ExecutionResult[T]:
        attempts = 0
        trace: list[str] = []
        last_error: Optional[Exception] = None
        for attempt in range(policy.retry + 1):
            attempts = attempt + 1
            try:
                value = await asyncio.wait_for(func(), timeout=policy.timeout_seconds)
                trace.append(f"{policy.name}:attempt={attempts}:ok")
                return ExecutionResult(ok=True, value=value, attempts=attempts, trace=trace)
            except Exception as exc:
                last_error = exc
                trace.append(f"{policy.name}:attempt={attempts}:error={type(exc).__name__}")

        if policy.fallback is not None:
            try:
                value = await asyncio.wait_for(policy.fallback(), timeout=policy.timeout_seconds)
                trace.append(f"{policy.name}:fallback:ok")
                return ExecutionResult(
                    ok=True,
                    value=value,
                    error=last_error,
                    attempts=attempts,
                    used_fallback=True,
                    trace=trace,
                )
            except Exception as exc:
                last_error = exc
                trace.append(f"{policy.name}:fallback:error={type(exc).__name__}")

        return ExecutionResult(ok=False, error=last_error, attempts=attempts, trace=trace)


