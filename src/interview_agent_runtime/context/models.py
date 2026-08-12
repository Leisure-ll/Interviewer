from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from interview_agent_runtime.artifacts import (
    AnswerArtifact,
    EvaluationArtifact,
    Evidence,
    FollowUpDecisionArtifact,
    QuestionArtifact,
)
from interview_agent_runtime.domain import (
    CapabilityProfile,
    CandidateProfile,
    InterviewDimension,
    InterviewPlan,
    InterviewStage,
    PositionProfile,
)


@dataclass
class AgentContext:
    session_id: str
    agent_name: str
    skill_name: str
    stage: InterviewStage
    authorized_tools: set[str]
    token_budget: int
    timeout_seconds: float
    retry: int


@dataclass
class ProfileAgentContext(AgentContext):
    raw_resume: dict[str, Any] = field(default_factory=dict)
    raw_jd: dict[str, Any] = field(default_factory=dict)


@dataclass
class PlannerAgentContext(AgentContext):
    candidate_profile: Optional[CandidateProfile] = None
    position_profile: Optional[PositionProfile] = None
    capability_profile: CapabilityProfile = field(default_factory=CapabilityProfile)
    important_evidence: list[Evidence] = field(default_factory=list)
    current_plan: Optional[InterviewPlan] = None


@dataclass
class QuestionAgentContext(AgentContext):
    candidate_profile: Optional[CandidateProfile] = None
    position_profile: Optional[PositionProfile] = None
    current_dimension: Optional[InterviewDimension] = None
    current_plan: Optional[InterviewPlan] = None
    capability_profile: CapabilityProfile = field(default_factory=CapabilityProfile)
    missing_or_unverified_skills: list[str] = field(default_factory=list)
    important_evidence: list[Evidence] = field(default_factory=list)
    recent_questions: list[QuestionArtifact] = field(default_factory=list)


@dataclass
class EvaluationAgentContext(AgentContext):
    current_question: Optional[QuestionArtifact] = None
    current_answer: Optional[AnswerArtifact] = None
    reference_answer: str = ""
    expected_points: list[str] = field(default_factory=list)
    current_dimension: str = ""
    relevant_evidence: list[Evidence] = field(default_factory=list)
    rubric: str = ""


@dataclass
class FollowUpAgentContext(AgentContext):
    current_question: Optional[QuestionArtifact] = None
    current_answer: Optional[AnswerArtifact] = None
    current_evaluation: Optional[EvaluationArtifact] = None
    missing_points: list[str] = field(default_factory=list)
    relevant_evidence: list[Evidence] = field(default_factory=list)
    current_dimension: str = ""
    follow_up_history: list[FollowUpDecisionArtifact] = field(default_factory=list)
    capability_summary: dict[str, Any] = field(default_factory=dict)
    follow_up_budget: int = 0
    dimension_follow_up_budget: int = 0


@dataclass
class ReportAgentContext(AgentContext):
    plan_summary: list[dict[str, Any]] = field(default_factory=list)
    capability_profile: CapabilityProfile = field(default_factory=CapabilityProfile)
    dimension_scores: dict[str, float] = field(default_factory=dict)
    dimension_coverage: dict[str, float] = field(default_factory=dict)
    key_evidence: list[Evidence] = field(default_factory=list)
    evaluation_summary: list[dict[str, Any]] = field(default_factory=list)
