from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from interview_agent_runtime.domain import CandidateProfile, InterviewPlan, PositionProfile


def artifact_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


@dataclass
class AgentArtifact:
    kind: str
    owner: str
    id: str = field(default_factory=lambda: artifact_id("artifact"))
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CandidateProfileArtifact(AgentArtifact):
    candidate_profile: CandidateProfile = field(default_factory=lambda: CandidateProfile(candidate_id="candidate"))
    position_profile: Optional[PositionProfile] = None
    resume_id: str = ""

    def __init__(
        self,
        owner: str,
        candidate_profile: Optional[CandidateProfile] = None,
        position_profile: Optional[PositionProfile] = None,
        resume_id: str = "",
        confidence: float = 1.0,
    ):
        super().__init__(kind="candidate_profile", owner=owner, confidence=confidence)
        self.candidate_profile = candidate_profile or CandidateProfile(candidate_id="candidate")
        self.position_profile = position_profile
        self.resume_id = resume_id

    @property
    def skills(self) -> list[str]:
        return self.candidate_profile.skills


@dataclass
class InterviewPlanArtifact(AgentArtifact):
    plan: InterviewPlan = field(default_factory=lambda: InterviewPlan([], 0, 0, 0))

    def __init__(self, owner: str, plan: InterviewPlan, confidence: float = 1.0):
        super().__init__(kind="interview_plan", owner=owner, confidence=confidence)
        self.plan = plan

    @property
    def dimensions(self) -> list[dict[str, Any]]:
        return [dict(item.__dict__) for item in self.plan.dimensions]

    @property
    def total_question_budget(self) -> int:
        return self.plan.total_question_budget

    @property
    def total_follow_up_budget(self) -> int:
        return self.plan.total_follow_up_budget


@dataclass
class QuestionArtifact(AgentArtifact):
    question_id: str = ""
    title: str = ""
    text: str = ""
    description: str = ""
    dimension: str = ""
    difficulty: str = "medium"
    question_type: str = "technical"
    reference_answer: str = ""
    source: str = "llm"
    is_follow_up: bool = False
    target_evidence: list[str] = field(default_factory=list)
    expected_points: list[str] = field(default_factory=list)
    related_skills: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    parent_question_id: Optional[str] = None

    def __init__(
        self,
        owner: str,
        question_id: str,
        title: str,
        dimension: str,
        text: Optional[str] = None,
        description: str = "",
        difficulty: str = "medium",
        question_type: str = "technical",
        reference_answer: str = "",
        source: str = "llm",
        is_follow_up: bool = False,
        target_evidence: Optional[list[str]] = None,
        expected_points: Optional[list[str]] = None,
        related_skills: Optional[list[str]] = None,
        tags: Optional[list[str]] = None,
        parent_question_id: Optional[str] = None,
    ):
        super().__init__(kind="question", owner=owner)
        self.question_id = question_id
        self.title = title
        self.text = text or title
        self.description = description
        self.dimension = dimension
        self.difficulty = difficulty
        self.question_type = question_type
        self.reference_answer = reference_answer
        self.source = source
        self.is_follow_up = is_follow_up
        self.target_evidence = target_evidence or []
        self.expected_points = expected_points or list(self.target_evidence)
        self.related_skills = related_skills or []
        self.tags = tags or []
        self.parent_question_id = parent_question_id


@dataclass
class AnswerArtifact(AgentArtifact):
    question_id: str = ""
    answer_id: str = ""
    text: str = ""
    normalized_text: str = ""
    source: str = "text"
    duration_seconds: Optional[float] = None

    def __init__(
        self,
        owner: str,
        question_id: str,
        text: str,
        source: str = "text",
        duration_seconds: Optional[float] = None,
    ):
        super().__init__(kind="answer", owner=owner)
        self.question_id = question_id
        self.answer_id = artifact_id("answer")
        self.text = text
        self.normalized_text = " ".join(text.strip().split())
        self.source = source
        self.duration_seconds = duration_seconds


@dataclass
class Evidence:
    dimension: str
    claim: str
    source_answer_id: str
    quote_or_summary: str
    confidence: float
    evidence_id: str = field(default_factory=lambda: artifact_id("evidence"))
    skill: Optional[str] = None
    source_question_id: str = ""
    answer_excerpt: str = ""
    evidence_type: str = "positive"
    polarity: str = "positive"


@dataclass
class EvaluationArtifact(AgentArtifact):
    question_id: str = ""
    answer_id: str = ""
    score: float = 0.0
    overall_score: float = 0.0
    dimension_scores: dict[str, float] = field(default_factory=dict)
    strengths: list[str] = field(default_factory=list)
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
        strengths: Optional[list[str]] = None,
        confidence: float = 1.0,
        need_follow_up: bool = False,
        follow_up_target: Optional[str] = None,
    ):
        super().__init__(kind="evaluation", owner=owner, confidence=confidence)
        self.question_id = question_id
        self.answer_id = answer_id
        self.score = score
        self.overall_score = score
        self.dimension_scores = dimension_scores
        self.evidence = evidence
        self.missing_points = missing_points or []
        self.strengths = strengths or []
        self.need_follow_up = need_follow_up
        self.follow_up_target = follow_up_target


@dataclass
class FollowUpDecisionArtifact(AgentArtifact):
    question_id: str = ""
    need_follow_up: bool = False
    target: Optional[str] = None
    normalized_target: str = ""
    reason: Optional[str] = None
    missing_evidence: list[str] = field(default_factory=list)

    def __init__(
        self,
        owner: str,
        question_id: str,
        need_follow_up: bool,
        confidence: float,
        target: Optional[str] = None,
        reason: Optional[str] = None,
        missing_evidence: Optional[list[str]] = None,
    ):
        super().__init__(kind="follow_up_decision", owner=owner, confidence=confidence)
        self.question_id = question_id
        self.need_follow_up = need_follow_up
        self.target = target
        self.normalized_target = normalize_follow_up_target(target or "")
        self.reason = reason
        self.missing_evidence = missing_evidence or []


@dataclass
class InterviewReportArtifact(AgentArtifact):
    overall_score: float = 0.0
    role_match_score: float = 0.0
    role_match: str = ""
    dimension_scores: dict[str, float] = field(default_factory=dict)
    verified_strengths: list[str] = field(default_factory=list)
    verified_skills: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    weak_skills: list[str] = field(default_factory=list)
    insufficient_evidence_areas: list[str] = field(default_factory=list)
    key_evidence: list[Evidence] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    interview_summary: str = ""
    hiring_recommendation: str = ""
    improvement_suggestions: list[str] = field(default_factory=list)

    def __init__(
        self,
        owner: str,
        overall_score: float,
        dimension_scores: dict[str, float],
        verified_skills: list[str],
        weak_skills: list[str],
        evidence: list[Evidence],
        role_match: str = "",
        role_match_score: Optional[float] = None,
        insufficient_evidence_areas: Optional[list[str]] = None,
        interview_summary: str = "",
        hiring_recommendation: str = "",
        improvement_suggestions: Optional[list[str]] = None,
    ):
        super().__init__(kind="interview_report", owner=owner)
        self.overall_score = overall_score
        self.role_match_score = role_match_score if role_match_score is not None else overall_score
        self.role_match = role_match
        self.dimension_scores = dimension_scores
        self.verified_skills = verified_skills
        self.verified_strengths = verified_skills
        self.weak_skills = weak_skills
        self.weaknesses = weak_skills
        self.insufficient_evidence_areas = insufficient_evidence_areas or []
        self.evidence = evidence
        self.key_evidence = evidence[:8]
        self.interview_summary = interview_summary
        self.hiring_recommendation = hiring_recommendation
        self.improvement_suggestions = improvement_suggestions or []


def normalize_follow_up_target(value: str) -> str:
    return "".join(ch.lower() for ch in value.strip() if ch.isalnum())
