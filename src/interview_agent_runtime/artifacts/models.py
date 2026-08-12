from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4


def _artifact_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


@dataclass
class AgentArtifact:
    kind: str
    owner: str
    id: str = field(default_factory=lambda: _artifact_id("artifact"))
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CandidateProfileArtifact(AgentArtifact):
    resume_id: str = ""
    skills: list[str] = field(default_factory=list)
    project_experience: list[str] = field(default_factory=list)
    risk_notes: list[str] = field(default_factory=list)

    def __init__(self, owner: str, resume_id: str = "", skills: Optional[list[str]] = None):
        super().__init__(kind="candidate_profile", owner=owner)
        self.resume_id = resume_id
        self.skills = skills or []
        self.project_experience = []
        self.risk_notes = []


@dataclass
class InterviewPlanArtifact(AgentArtifact):
    dimensions: list[dict[str, Any]] = field(default_factory=list)
    total_question_budget: int = 0
    total_follow_up_budget: int = 0

    def __init__(
        self,
        owner: str,
        dimensions: list[dict[str, Any]],
        total_question_budget: int,
        total_follow_up_budget: int,
    ):
        super().__init__(kind="interview_plan", owner=owner)
        self.dimensions = dimensions
        self.total_question_budget = total_question_budget
        self.total_follow_up_budget = total_follow_up_budget


@dataclass
class QuestionArtifact(AgentArtifact):
    question_id: str = ""
    title: str = ""
    description: str = ""
    dimension: str = ""
    difficulty: str = "medium"
    reference_answer: str = ""
    source: str = "llm"
    is_follow_up: bool = False

    def __init__(
        self,
        owner: str,
        question_id: str,
        title: str,
        dimension: str,
        description: str = "",
        difficulty: str = "medium",
        reference_answer: str = "",
        source: str = "llm",
        is_follow_up: bool = False,
    ):
        super().__init__(kind="question", owner=owner)
        self.question_id = question_id
        self.title = title
        self.description = description
        self.dimension = dimension
        self.difficulty = difficulty
        self.reference_answer = reference_answer
        self.source = source
        self.is_follow_up = is_follow_up


@dataclass
class AnswerArtifact(AgentArtifact):
    question_id: str = ""
    answer_id: str = ""
    text: str = ""

    def __init__(self, owner: str, question_id: str, text: str):
        super().__init__(kind="answer", owner=owner)
        self.question_id = question_id
        self.answer_id = _artifact_id("answer")
        self.text = text


@dataclass
class Evidence:
    dimension: str
    claim: str
    source_answer_id: str
    quote_or_summary: str
    confidence: float


@dataclass
class EvaluationArtifact(AgentArtifact):
    question_id: str = ""
    answer_id: str = ""
    score: float = 0.0
    dimension_scores: dict[str, float] = field(default_factory=dict)
    evidence: list[Evidence] = field(default_factory=list)
    missing_points: list[str] = field(default_factory=list)
    need_follow_up: bool = False
    follow_up_target: Optional[str] = None

    def __init__(
        self,
        owner: str,
        question_id: str,
        answer_id: str,
        score: float,
        dimension_scores: dict[str, float],
        evidence: list[Evidence],
        missing_points: Optional[list[str]] = None,
        confidence: float = 1.0,
        need_follow_up: bool = False,
        follow_up_target: Optional[str] = None,
    ):
        super().__init__(kind="evaluation", owner=owner, confidence=confidence)
        self.question_id = question_id
        self.answer_id = answer_id
        self.score = score
        self.dimension_scores = dimension_scores
        self.evidence = evidence
        self.missing_points = missing_points or []
        self.need_follow_up = need_follow_up
        self.follow_up_target = follow_up_target


@dataclass
class FollowUpDecisionArtifact(AgentArtifact):
    question_id: str = ""
    need_follow_up: bool = False
    target: str = ""
    reason: str = ""
    missing_evidence: list[str] = field(default_factory=list)

    def __init__(
        self,
        owner: str,
        question_id: str,
        need_follow_up: bool,
        confidence: float,
        target: str = "",
        reason: str = "",
        missing_evidence: Optional[list[str]] = None,
    ):
        super().__init__(kind="follow_up_decision", owner=owner, confidence=confidence)
        self.question_id = question_id
        self.need_follow_up = need_follow_up
        self.target = target
        self.reason = reason
        self.missing_evidence = missing_evidence or []


@dataclass
class InterviewReportArtifact(AgentArtifact):
    overall_score: float = 0.0
    dimension_scores: dict[str, float] = field(default_factory=dict)
    verified_skills: list[str] = field(default_factory=list)
    weak_skills: list[str] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)

    def __init__(
        self,
        owner: str,
        overall_score: float,
        dimension_scores: dict[str, float],
        verified_skills: list[str],
        weak_skills: list[str],
        evidence: list[Evidence],
    ):
        super().__init__(kind="interview_report", owner=owner)
        self.overall_score = overall_score
        self.dimension_scores = dimension_scores
        self.verified_skills = verified_skills
        self.weak_skills = weak_skills
        self.evidence = evidence

