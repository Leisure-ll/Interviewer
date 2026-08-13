from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Optional

from interview_agent_runtime.messages import AgentMessage


@dataclass(frozen=True)
class MemoryScope:
    """Stable namespace for one agent's interaction history in one session."""

    session_id: str
    agent_name: str

    def key(self) -> str:
        return f"{self.session_id}:{self.agent_name}"


@dataclass
class InterviewMemorySnapshot:
    """Capability-oriented memory of interview domain state.

    This deliberately stores capability facts rather than a transcript summary.
    """

    verified_skills: list[str] = field(default_factory=list)
    weak_skills: list[str] = field(default_factory=list)
    uncertain_skills: list[str] = field(default_factory=list)
    dimension_scores: dict[str, float] = field(default_factory=dict)
    dimension_coverage: dict[str, float] = field(default_factory=dict)
    key_evidence: list[str] = field(default_factory=list)
    unresolved_gaps: list[str] = field(default_factory=list)
    recent_question_ids: list[str] = field(default_factory=list)
    current_dimension: Optional[str] = None

    @classmethod
    def from_blackboard(cls, blackboard: Any, max_evidence: int = 8) -> "InterviewMemorySnapshot":
        evidence = sorted(
            getattr(blackboard, "evidence", []),
            key=lambda item: (
                getattr(item, "polarity", "") != "positive",
                -float(getattr(item, "confidence", 0.0)),
            ),
        )
        capability = getattr(blackboard, "capability_profile", None)
        plan = getattr(blackboard, "plan", None)
        gaps: list[str] = []
        if capability is not None:
            gaps.extend(getattr(capability, "weak_skills", []))
            for item in getattr(capability, "uncertain_skills", []):
                if item not in gaps:
                    gaps.append(item)
        if plan is not None:
            for dimension in getattr(plan, "dimensions", []):
                name = getattr(dimension, "name", "")
                if (
                    name
                    and name not in getattr(blackboard, "dimension_coverage", {})
                    and name not in gaps
                ):
                    gaps.append(name)
        return cls(
            verified_skills=list(getattr(capability, "verified_skills", [])) if capability else [],
            weak_skills=list(getattr(capability, "weak_skills", [])) if capability else [],
            uncertain_skills=list(getattr(capability, "uncertain_skills", [])) if capability else [],
            dimension_scores=dict(getattr(blackboard, "dimension_scores", {})),
            dimension_coverage=dict(getattr(blackboard, "dimension_coverage", {})),
            key_evidence=[
                str(getattr(item, "claim", ""))
                for item in evidence[:max_evidence]
                if getattr(item, "claim", "")
            ],
            unresolved_gaps=gaps,
            recent_question_ids=[
                str(getattr(item, "question_id", ""))
                for item in getattr(blackboard, "question_history", [])[-5:]
                if getattr(item, "question_id", "")
            ],
            current_dimension=getattr(blackboard, "current_dimension", None) or None,
        )

    def is_empty(self) -> bool:
        return not any(
            [
                self.verified_skills,
                self.weak_skills,
                self.uncertain_skills,
                self.dimension_scores,
                self.dimension_coverage,
                self.key_evidence,
                self.unresolved_gaps,
                self.recent_question_ids,
                self.current_dimension,
            ]
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "verified_skills": list(self.verified_skills),
            "weak_skills": list(self.weak_skills),
            "uncertain_skills": list(self.uncertain_skills),
            "dimension_scores": dict(self.dimension_scores),
            "dimension_coverage": dict(self.dimension_coverage),
            "key_evidence": list(self.key_evidence),
            "unresolved_gaps": list(self.unresolved_gaps),
            "recent_question_ids": list(self.recent_question_ids),
            "current_dimension": self.current_dimension,
        }


@dataclass
class MemoryContext:
    summary: Optional[AgentMessage] = None
    recent_messages: list[AgentMessage] = field(default_factory=list)
    domain_snapshot: Optional[InterviewMemorySnapshot] = None

    def to_messages(self, max_chars: Optional[int] = None) -> list[AgentMessage]:
        domain_messages: list[AgentMessage] = []
        if self.domain_snapshot is not None and not self.domain_snapshot.is_empty():
            domain_messages.append(
                AgentMessage.system(
                    "Interview capability snapshot:\n"
                    + json.dumps(self.domain_snapshot.to_dict(), ensure_ascii=False)
                )
            )
        history_messages = ([self.summary] if self.summary is not None else []) + list(
            self.recent_messages
        )
        if max_chars is None:
            return domain_messages + history_messages

        # Domain facts outrank interaction history. Trim old history first and
        # leave the current invocation messages to the caller.
        used = sum(len(message.content or "") for message in domain_messages)
        kept: list[AgentMessage] = []
        for message in reversed(history_messages):
            size = len(message.content or "")
            if kept and used + size > max_chars:
                continue
            kept.append(message)
            used += size
        return domain_messages + list(reversed(kept))

    @property
    def has_history(self) -> bool:
        return self.summary is not None or bool(self.recent_messages)


def stable_content_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
