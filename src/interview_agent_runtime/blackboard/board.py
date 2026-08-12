from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

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
from interview_agent_runtime.runtime.states import InterviewStage


@dataclass
class RuntimeMetadata:
    runtime_version: str = "0.1.0"
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    trace_id: str = ""
    errors: list[str] = field(default_factory=list)


@dataclass
class InterviewBlackboard:
    session_id: str
    candidate_profile: Optional[CandidateProfileArtifact] = None
    position_profile: Optional[dict[str, Any]] = None
    interview_plan: Optional[InterviewPlanArtifact] = None
    current_stage: InterviewStage = InterviewStage.INIT
    current_dimension: str = ""
    current_question: Optional[QuestionArtifact] = None
    answers: list[AnswerArtifact] = field(default_factory=list)
    evaluations: list[EvaluationArtifact] = field(default_factory=list)
    follow_up_decisions: list[FollowUpDecisionArtifact] = field(default_factory=list)
    report: Optional[InterviewReportArtifact] = None
    evidence: list[Evidence] = field(default_factory=list)
    dimension_scores: dict[str, float] = field(default_factory=dict)
    dimension_coverage: dict[str, float] = field(default_factory=dict)
    follow_up_budget: int = 0
    question_budget: int = 0
    token_budget: int = 0
    asked_question_ids: set[str] = field(default_factory=set)
    followed_targets: set[str] = field(default_factory=set)
    runtime_metadata: RuntimeMetadata = field(default_factory=RuntimeMetadata)

    def publish(self, artifact: AgentArtifact) -> None:
        self.runtime_metadata.updated_at = datetime.now(timezone.utc)
        if isinstance(artifact, CandidateProfileArtifact):
            self.candidate_profile = artifact
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
            return
        if isinstance(artifact, AnswerArtifact):
            self.answers.append(artifact)
            return
        if isinstance(artifact, EvaluationArtifact):
            self.evaluations.append(artifact)
            self.evidence.extend(artifact.evidence)
            self.dimension_scores.update(artifact.dimension_scores)
            for dimension in artifact.dimension_scores:
                self.dimension_coverage[dimension] = min(
                    1.0,
                    self.dimension_coverage.get(dimension, 0.0) + 0.35,
                )
            return
        if isinstance(artifact, FollowUpDecisionArtifact):
            self.follow_up_decisions.append(artifact)
            return
        if isinstance(artifact, InterviewReportArtifact):
            self.report = artifact
            return
        raise TypeError(f"Unsupported artifact type: {type(artifact)!r}")

    @property
    def latest_answer(self) -> Optional[AnswerArtifact]:
        return self.answers[-1] if self.answers else None

    @property
    def latest_evaluation(self) -> Optional[EvaluationArtifact]:
        return self.evaluations[-1] if self.evaluations else None

    @property
    def latest_follow_up_decision(self) -> Optional[FollowUpDecisionArtifact]:
        return self.follow_up_decisions[-1] if self.follow_up_decisions else None


