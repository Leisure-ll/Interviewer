from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from interview_agent_runtime.artifacts import (
    AgentArtifact,
    AnswerArtifact,
    CandidateProfileArtifact,
    EvaluationArtifact,
    Evidence,
    FollowUpDecisionArtifact,
    InterviewPlanArtifact,
    InterviewReportArtifact,
    QuestionArtifact,
)
from interview_agent_runtime.domain import CapabilityProfile, CandidateProfile, InterviewPlan, InterviewStage, PositionProfile


@dataclass
class RuntimeMetadata:
    runtime_version: str = "0.2.0"
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    trace_id: str = ""
    errors: list[str] = field(default_factory=list)
    max_follow_up_round_per_question: int = 2
    session_timeout_seconds: int = 1800


@dataclass
class InterviewBlackboard:
    session_id: str
    candidate_profile: Optional[CandidateProfileArtifact] = None
    position_profile: Optional[PositionProfile] = None
    interview_plan: Optional[InterviewPlanArtifact] = None
    current_stage: InterviewStage = InterviewStage.INIT
    current_dimension: str = ""
    current_question: Optional[QuestionArtifact] = None
    answers: list[AnswerArtifact] = field(default_factory=list)
    evaluations: list[EvaluationArtifact] = field(default_factory=list)
    follow_up_decisions: list[FollowUpDecisionArtifact] = field(default_factory=list)
    report: Optional[InterviewReportArtifact] = None
    evidence: list[Evidence] = field(default_factory=list)
    capability_profile: CapabilityProfile = field(default_factory=CapabilityProfile)
    follow_up_budget: int = 0
    question_budget: int = 0
    token_budget: int = 0
    asked_question_ids: set[str] = field(default_factory=set)
    followed_targets: set[str] = field(default_factory=set)
    question_follow_up_rounds: dict[str, int] = field(default_factory=dict)
    runtime_metadata: RuntimeMetadata = field(default_factory=RuntimeMetadata)

    @property
    def candidate(self) -> Optional[CandidateProfile]:
        return self.candidate_profile.candidate_profile if self.candidate_profile else None

    @property
    def plan(self) -> Optional[InterviewPlan]:
        return self.interview_plan.plan if self.interview_plan else None

    @property
    def dimension_scores(self) -> dict[str, float]:
        return self.capability_profile.dimension_scores

    @property
    def dimension_coverage(self) -> dict[str, float]:
        return self.capability_profile.dimension_coverage

    def publish(self, artifact: AgentArtifact) -> None:
        self.runtime_metadata.updated_at = datetime.now(timezone.utc)
        if isinstance(artifact, CandidateProfileArtifact):
            self.candidate_profile = artifact
            if artifact.position_profile is not None:
                self.position_profile = artifact.position_profile
            return
        if isinstance(artifact, InterviewPlanArtifact):
            self.interview_plan = artifact
            self.question_budget = artifact.total_question_budget
            self.follow_up_budget = artifact.total_follow_up_budget
            return
        if isinstance(artifact, QuestionArtifact):
            self.current_question = artifact
            self.current_dimension = artifact.dimension
            self.asked_question_ids.add(artifact.question_id)
            if artifact.is_follow_up:
                parent_id = artifact.parent_question_id or artifact.question_id
                self.question_follow_up_rounds[parent_id] = self.question_follow_up_rounds.get(parent_id, 0) + 1
            else:
                self.question_budget = max(0, self.question_budget - 1)
                if self.plan is not None:
                    self.plan.mark_question_asked(artifact.dimension)
            return
        if isinstance(artifact, AnswerArtifact):
            self.answers.append(artifact)
            return
        if isinstance(artifact, EvaluationArtifact):
            self.evaluations.append(artifact)
            self.evidence.extend(artifact.evidence)
            for dimension, score in artifact.dimension_scores.items():
                count = len([item for item in artifact.evidence if item.dimension == dimension])
                self.capability_profile.update_dimension(dimension, score, count, artifact.missing_points)
                if self.plan is not None:
                    self.plan.mark_dimension_if_covered(dimension, self.capability_profile.dimension_coverage.get(dimension, 0.0))
            return
        if isinstance(artifact, FollowUpDecisionArtifact):
            self.follow_up_decisions.append(artifact)
            return
        if isinstance(artifact, InterviewReportArtifact):
            self.report = artifact
            return
        raise TypeError(f"Unsupported artifact type: {type(artifact)!r}")

    def current_question_follow_up_round(self) -> int:
        if self.current_question is None:
            return 0
        question_id = self.current_question.parent_question_id or self.current_question.question_id
        return self.question_follow_up_rounds.get(question_id, 0)

    def session_not_timeout(self) -> bool:
        elapsed = (datetime.now(timezone.utc) - self.runtime_metadata.started_at).total_seconds()
        return elapsed <= self.runtime_metadata.session_timeout_seconds

    @property
    def latest_answer(self) -> Optional[AnswerArtifact]:
        return self.answers[-1] if self.answers else None

    @property
    def latest_evaluation(self) -> Optional[EvaluationArtifact]:
        return self.evaluations[-1] if self.evaluations else None

    @property
    def latest_follow_up_decision(self) -> Optional[FollowUpDecisionArtifact]:
        return self.follow_up_decisions[-1] if self.follow_up_decisions else None
