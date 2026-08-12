from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from interview_agent_runtime.blackboard import InterviewBlackboard
from interview_agent_runtime.context.models import (
    AgentContext,
    EvaluationAgentContext,
    FollowUpAgentContext,
    PlannerAgentContext,
    ProfileAgentContext,
    QuestionAgentContext,
    ReportAgentContext,
)
from interview_agent_runtime.domain import InterviewDimension
from interview_agent_runtime.context.execution import ExecutionContext


@dataclass
class ContextBudget:
    max_recent_questions: int = 5
    max_recent_answers: int = 3
    max_evidence_items: int = 8
    max_context_tokens: int = 2500


class AgentContextBuilder:
    def __init__(self, budget: Optional[ContextBudget] = None) -> None:
        self.budget = budget or ContextBudget()

    def build(
        self,
        agent_name: str,
        blackboard: InterviewBlackboard,
        execution_context: ExecutionContext,
    ) -> AgentContext:
        common = {
            "session_id": blackboard.session_id,
            "agent_name": agent_name,
            "skill_name": execution_context.current_skill,
            "stage": blackboard.current_stage,
            "authorized_tools": set(execution_context.authorized_tools),
            "token_budget": execution_context.token_budget,
            "timeout_seconds": execution_context.timeout_seconds,
            "retry": execution_context.retry,
        }
        if agent_name == "ProfileAgent":
            return ProfileAgentContext(
                **common,
                raw_resume=dict(blackboard.session_inputs.get("resume", {})),
                raw_jd=dict(blackboard.session_inputs.get("jd", {})),
            )
        if agent_name == "PlannerAgent":
            return PlannerAgentContext(
                **common,
                candidate_profile=blackboard.candidate,
                position_profile=blackboard.position_profile,
                capability_profile=blackboard.capability_profile,
                important_evidence=self._important_evidence(blackboard),
                current_plan=blackboard.plan,
            )
        if agent_name == "QuestionAgent":
            return QuestionAgentContext(
                **common,
                candidate_profile=blackboard.candidate,
                position_profile=blackboard.position_profile,
                current_dimension=self._current_dimension(blackboard),
                current_plan=blackboard.plan,
                capability_profile=blackboard.capability_profile,
                missing_or_unverified_skills=self._missing_or_unverified(blackboard),
                important_evidence=self._important_evidence(blackboard),
                recent_questions=blackboard.question_history[-self.budget.max_recent_questions :],
            )
        if agent_name == "EvaluatorAgent":
            question = blackboard.current_question
            return EvaluationAgentContext(
                **common,
                current_question=question,
                current_answer=blackboard.latest_answer,
                reference_answer=question.reference_answer if question else "",
                expected_points=list(question.expected_points if question else []),
                current_dimension=blackboard.current_dimension,
                relevant_evidence=self._relevant_evidence(blackboard, blackboard.current_dimension),
            )
        if agent_name == "FollowUpAgent":
            evaluation = blackboard.latest_evaluation
            return FollowUpAgentContext(
                **common,
                current_question=blackboard.current_question,
                current_answer=blackboard.latest_answer,
                current_evaluation=evaluation,
                missing_points=list(evaluation.missing_points if evaluation else []),
                relevant_evidence=self._relevant_evidence(blackboard, blackboard.current_dimension),
                current_dimension=blackboard.current_dimension,
                follow_up_history=blackboard.follow_up_decisions[-self.budget.max_recent_questions :],
            )
        if agent_name == "ReportAgent":
            return ReportAgentContext(
                **common,
                plan_summary=self._plan_summary(blackboard),
                capability_profile=blackboard.capability_profile,
                dimension_scores=dict(blackboard.dimension_scores),
                dimension_coverage=dict(blackboard.dimension_coverage),
                key_evidence=self._important_evidence(blackboard),
                evaluation_summary=self._evaluation_summary(blackboard),
            )
        return AgentContext(**common)

    def capability_summary(self, blackboard: InterviewBlackboard) -> dict[str, object]:
        return {
            "verified_skills": list(blackboard.capability_profile.verified_skills),
            "weak_skills": list(blackboard.capability_profile.weak_skills),
            "uncertain_skills": list(blackboard.capability_profile.uncertain_skills),
            "dimension_coverage": dict(blackboard.dimension_coverage),
            "key_evidence": [item.claim for item in self._important_evidence(blackboard)],
            "unresolved_gaps": self._missing_or_unverified(blackboard),
        }

    def _current_dimension(self, blackboard: InterviewBlackboard) -> Optional[InterviewDimension]:
        if blackboard.plan is None:
            return None
        if blackboard.current_dimension:
            for item in blackboard.plan.dimensions:
                if item.name == blackboard.current_dimension:
                    return item
        return blackboard.plan.next_dimension(blackboard.dimension_coverage)

    def _important_evidence(self, blackboard: InterviewBlackboard):
        evidence = sorted(
            blackboard.evidence,
            key=lambda item: (item.polarity != "positive", -item.confidence),
        )
        return evidence[: self.budget.max_evidence_items]

    def _relevant_evidence(self, blackboard: InterviewBlackboard, dimension: str):
        return [
            item
            for item in blackboard.evidence
            if item.dimension == dimension
        ][-self.budget.max_evidence_items :]

    def _missing_or_unverified(self, blackboard: InterviewBlackboard) -> list[str]:
        gaps = list(blackboard.capability_profile.weak_skills)
        gaps.extend(item for item in blackboard.capability_profile.uncertain_skills if item not in gaps)
        if blackboard.plan:
            for dimension in blackboard.plan.dimensions:
                if dimension.name not in blackboard.dimension_coverage and dimension.name not in gaps:
                    gaps.append(dimension.name)
        return gaps

    def _plan_summary(self, blackboard: InterviewBlackboard) -> list[dict[str, object]]:
        if blackboard.plan is None:
            return []
        return [
            {
                "name": item.name,
                "weight": item.weight,
                "difficulty": item.difficulty,
                "coverage": item.current_coverage,
                "coverage_target": item.coverage_target,
                "completed": item.completed,
            }
            for item in blackboard.plan.dimensions
        ]

    def _evaluation_summary(self, blackboard: InterviewBlackboard) -> list[dict[str, object]]:
        return [
            {
                "question_id": item.question_id,
                "score": item.overall_score,
                "missing_points": list(item.missing_points),
                "evidence_count": len(item.evidence),
            }
            for item in blackboard.evaluations[-self.budget.max_recent_answers :]
        ]
