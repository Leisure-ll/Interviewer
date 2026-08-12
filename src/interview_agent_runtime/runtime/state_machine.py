from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from interview_agent_runtime.artifacts import (
    AgentArtifact,
    AnswerArtifact,
    EvaluationArtifact,
    FollowUpDecisionArtifact,
    InterviewPlanArtifact,
    InterviewReportArtifact,
    QuestionArtifact,
)
from interview_agent_runtime.blackboard import InterviewBlackboard
from interview_agent_runtime.artifacts import normalize_follow_up_target
from interview_agent_runtime.runtime.states import InterviewStage


@dataclass
class TransitionGuard:
    follow_up_confidence_threshold: float = 0.55
    session_question_limit: int = 10
    max_follow_up_round_per_question: int = 2

    def allow_follow_up(self, context: InterviewBlackboard, decision: FollowUpDecisionArtifact) -> bool:
        if not decision.need_follow_up:
            return False
        if decision.confidence < self.follow_up_confidence_threshold:
            return False
        if context.follow_up_budget <= 0:
            return False
        if not context.session_not_timeout():
            return False
        if not decision.target:
            return False
        normalized_target = normalize_follow_up_target(decision.target)
        if normalized_target in context.followed_targets:
            return False
        if context.current_question_follow_up_round() >= self.max_follow_up_round_per_question:
            return False
        return True

    def allow_next_question(self, context: InterviewBlackboard) -> bool:
        has_dimension = True
        if context.plan is not None:
            has_dimension = context.plan.next_dimension(context.dimension_coverage) is not None
        return (
            context.question_budget > 0
            and has_dimension
            and len(context.asked_question_ids) < self.session_question_limit
            and context.session_not_timeout()
        )


class InterviewStateMachine:
    def __init__(self, guard: Optional[TransitionGuard] = None) -> None:
        self.guard = guard or TransitionGuard()

    def transition(
        self,
        state: InterviewStage,
        context: InterviewBlackboard,
        artifact: Optional[AgentArtifact],
    ) -> InterviewStage:
        if state == InterviewStage.INIT:
            return InterviewStage.PROFILE_ANALYSIS
        if state == InterviewStage.PROFILE_ANALYSIS:
            return InterviewStage.INTERVIEW_PLANNING
        if state == InterviewStage.INTERVIEW_PLANNING and isinstance(artifact, InterviewPlanArtifact):
            return InterviewStage.QUESTION_PREPARING
        if state in {InterviewStage.QUESTION_PREPARING, InterviewStage.NEXT_QUESTION, InterviewStage.FOLLOW_UP}:
            if isinstance(artifact, QuestionArtifact):
                return InterviewStage.QUESTIONING
            return InterviewStage.FAILED
        if state == InterviewStage.QUESTIONING:
            return InterviewStage.LISTENING
        if state == InterviewStage.LISTENING and isinstance(artifact, AnswerArtifact):
            return InterviewStage.EVALUATING
        if state == InterviewStage.EVALUATING and isinstance(artifact, EvaluationArtifact):
            return InterviewStage.DECISION
        if state == InterviewStage.DECISION and isinstance(artifact, FollowUpDecisionArtifact):
            if self.guard.allow_follow_up(context, artifact):
                context.follow_up_budget -= 1
                context.followed_targets.add(artifact.normalized_target)
                return InterviewStage.FOLLOW_UP
            if self.guard.allow_next_question(context):
                return InterviewStage.NEXT_QUESTION
            return InterviewStage.REPORTING
        if state == InterviewStage.REPORTING and isinstance(artifact, InterviewReportArtifact):
            return InterviewStage.FINISHED
        return InterviewStage.FAILED


