from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional, Protocol


class RuntimeEventType(str, Enum):
    SESSION_STARTED = "SESSION_STARTED"
    PROFILE_CREATED = "PROFILE_CREATED"
    PLAN_CREATED = "PLAN_CREATED"
    QUESTION_GENERATION_STARTED = "QUESTION_GENERATION_STARTED"
    QUESTION_GENERATED = "QUESTION_GENERATED"
    QUESTION_RETRIEVED = "QUESTION_RETRIEVED"
    QUESTION_FILTERED = "QUESTION_FILTERED"
    QUESTION_ASKED = "QUESTION_ASKED"
    ANSWER_RECEIVED = "ANSWER_RECEIVED"
    ANSWER_EVALUATED = "ANSWER_EVALUATED"
    EVIDENCE_CREATED = "EVIDENCE_CREATED"
    FOLLOW_UP_DECIDED = "FOLLOW_UP_DECIDED"
    FOLLOW_UP_TRIGGERED = "FOLLOW_UP_TRIGGERED"
    STATE_TRANSITIONED = "STATE_TRANSITIONED"
    TOOL_CALLED = "TOOL_CALLED"
    TOOL_SUCCEEDED = "TOOL_SUCCEEDED"
    TOOL_FAILED = "TOOL_FAILED"
    LLM_REQUESTED = "LLM_REQUESTED"
    LLM_RESPONDED = "LLM_RESPONDED"
    AGENT_LOOP_STARTED = "AGENT_LOOP_STARTED"
    AGENT_LOOP_FINISHED = "AGENT_LOOP_FINISHED"
    AGENT_LOOP_STOPPED = "AGENT_LOOP_STOPPED"
    AGENT_FALLBACK_USED = "AGENT_FALLBACK_USED"
    AGENT_STARTED = "AGENT_STARTED"
    AGENT_FINISHED = "AGENT_FINISHED"
    SKILL_LOADED = "SKILL_LOADED"
    CHECKPOINT_CREATED = "CHECKPOINT_CREATED"
    REPORT_GENERATED = "REPORT_GENERATED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    REVIEW_AUTO_COMPLETED = "REVIEW_AUTO_COMPLETED"
    HUMAN_REVIEW_SUBMITTED = "HUMAN_REVIEW_SUBMITTED"
    RUNTIME_ERROR = "RUNTIME_ERROR"


@dataclass(frozen=True)
class TraceContext:
    trace_id: str
    run_id: Optional[str] = None
    span_id: Optional[str] = None
    parent_span_id: Optional[str] = None


@dataclass
class RuntimeEvent:
    type: RuntimeEventType
    session_id: str
    message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    trace: Optional[TraceContext] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class EventBus(Protocol):
    async def emit(self, event: RuntimeEvent) -> None:
        ...


class InMemoryEventBus:
    def __init__(self, observer: Optional[Any] = None) -> None:
        self.events: list[RuntimeEvent] = []
        self.observer = observer
        self._session_traces: dict[str, TraceContext] = {}

    def bind_trace(self, session_id: str, trace: TraceContext) -> None:
        self._session_traces[session_id] = trace

    async def emit(self, event: RuntimeEvent) -> None:
        if event.trace is None and event.session_id in self._session_traces:
            event.trace = self._session_traces[event.session_id]
        self.events.append(event)
        if self.observer is not None:
            await self.observer.on_event(event)


