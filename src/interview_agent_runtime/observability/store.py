from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Protocol, Union

from interview_agent_runtime.observability.trace import RunTrace, TraceSpan


class TraceStore(Protocol):
    async def start_trace(self, trace: RunTrace) -> None:
        ...

    async def append_span(self, trace_id: str, span: TraceSpan) -> None:
        ...

    async def finish_span(self, trace_id: str, span_id: str, status: str = "ok") -> None:
        ...

    async def finish_trace(self, trace_id: str, status: str = "ok") -> None:
        ...

    async def load(self, trace_id: str) -> Optional[RunTrace]:
        ...


class InMemoryTraceStore:
    def __init__(self) -> None:
        self._items: dict[str, RunTrace] = {}

    async def start_trace(self, trace: RunTrace) -> None:
        self._items[trace.trace_id] = trace

    async def append_span(self, trace_id: str, span: TraceSpan) -> None:
        trace = self._items.setdefault(trace_id, RunTrace(trace_id=trace_id, session_id=""))
        trace.spans.append(span)

    async def finish_span(self, trace_id: str, span_id: str, status: str = "ok") -> None:
        trace = self._items.get(trace_id)
        if trace is None:
            return
        for span in reversed(trace.spans):
            if span.span_id == span_id and span.finished_at is None:
                span.finished_at = datetime.now(timezone.utc)
                span.status = status
                return

    async def finish_trace(self, trace_id: str, status: str = "ok") -> None:
        trace = self._items.get(trace_id)
        if trace is None:
            return
        trace.finished_at = datetime.now(timezone.utc)
        trace.status = status

    async def load(self, trace_id: str) -> Optional[RunTrace]:
        return self._items.get(trace_id)


class JsonFileTraceStore:
    def __init__(self, root: Union[str, Path]) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    async def start_trace(self, trace: RunTrace) -> None:
        await self._write(trace)

    async def append_span(self, trace_id: str, span: TraceSpan) -> None:
        trace = await self.load(trace_id) or RunTrace(trace_id=trace_id, session_id="")
        trace.spans.append(span)
        await self._write(trace)

    async def finish_span(self, trace_id: str, span_id: str, status: str = "ok") -> None:
        trace = await self.load(trace_id)
        if trace is None:
            return
        for span in reversed(trace.spans):
            if span.span_id == span_id and span.finished_at is None:
                span.finished_at = datetime.now(timezone.utc)
                span.status = status
                break
        await self._write(trace)

    async def finish_trace(self, trace_id: str, status: str = "ok") -> None:
        trace = await self.load(trace_id)
        if trace is None:
            return
        trace.finished_at = datetime.now(timezone.utc)
        trace.status = status
        await self._write(trace)

    async def load(self, trace_id: str) -> Optional[RunTrace]:
        path = self.root / f"{trace_id}.json"
        if not path.exists():
            return None
        return _trace_from_json(json.loads(path.read_text(encoding="utf-8")))

    async def _write(self, trace: RunTrace) -> None:
        path = self.root / f"{trace.trace_id}.json"
        path.write_text(json.dumps(_to_json(trace), ensure_ascii=False, indent=2), encoding="utf-8")


def _trace_from_json(data: dict[str, Any]) -> RunTrace:
    trace = RunTrace(
        trace_id=data["trace_id"],
        session_id=data.get("session_id", ""),
        status=data.get("status", "running"),
    )
    if data.get("started_at"):
        trace.started_at = datetime.fromisoformat(data["started_at"])
    if data.get("finished_at"):
        trace.finished_at = datetime.fromisoformat(data["finished_at"])
    trace.spans = [_span_from_json(item) for item in data.get("spans", [])]
    return trace


def _span_from_json(data: dict[str, Any]) -> TraceSpan:
    span = TraceSpan(
        span_id=data["span_id"],
        trace_id=data["trace_id"],
        parent_span_id=data.get("parent_span_id"),
        name=data.get("name", ""),
        kind=data.get("kind", ""),
        status=data.get("status", "running"),
        metadata=dict(data.get("metadata", {})),
    )
    if data.get("started_at"):
        span.started_at = datetime.fromisoformat(data["started_at"])
    if data.get("finished_at"):
        span.finished_at = datetime.fromisoformat(data["finished_at"])
    return span


def _to_json(value: Any) -> Any:
    if is_dataclass(value):
        return _to_json(asdict(value))
    if isinstance(value, dict):
        return {key: _to_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_json(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value
