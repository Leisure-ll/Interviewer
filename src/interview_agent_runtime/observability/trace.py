from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from interview_agent_runtime.runtime.events import TraceContext


@dataclass
class TraceSpan:
    span_id: str
    trace_id: str
    parent_span_id: Optional[str]
    name: str
    kind: str
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: Optional[datetime] = None
    status: str = "running"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RunTrace:
    trace_id: str
    session_id: str
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: Optional[datetime] = None
    status: str = "running"
    spans: list[TraceSpan] = field(default_factory=list)


__all__ = ["RunTrace", "TraceContext", "TraceSpan"]
