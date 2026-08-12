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
    TOOL_FAILED = "TOOL_FAILED"
    AGENT_STARTED = "AGENT_STARTED"
    AGENT_FINISHED = "AGENT_FINISHED"
    SKILL_LOADED = "SKILL_LOADED"
    CHECKPOINT_CREATED = "CHECKPOINT_CREATED"
    REPORT_GENERATED = "REPORT_GENERATED"
    RUNTIME_ERROR = "RUNTIME_ERROR"


@dataclass
class RuntimeEvent:
    type: RuntimeEventType
    session_id: str
    message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class EventBus(Protocol):
    async def emit(self, event: RuntimeEvent) -> None:
        ...


class InMemoryEventBus:
    def __init__(self, observer: Optional[Any] = None) -> None:
        self.events: list[RuntimeEvent] = []
        self.observer = observer

    async def emit(self, event: RuntimeEvent) -> None:
        self.events.append(event)
        if self.observer is not None:
            await self.observer.on_event(event)


