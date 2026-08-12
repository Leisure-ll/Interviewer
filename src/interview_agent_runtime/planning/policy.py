from __future__ import annotations

from dataclasses import dataclass

from interview_agent_runtime.artifacts import EvaluationArtifact
from interview_agent_runtime.domain import InterviewPlan


@dataclass
class InterviewPlanPolicy:
    weak_score_threshold: float = 65.0
    high_score_threshold: float = 82.0

    def update_after_evaluation(
        self,
        plan: InterviewPlan,
        evaluation: EvaluationArtifact,
        coverage: dict[str, float],
    ) -> int:
        released_budget = 0
        for dimension_name, score in evaluation.dimension_scores.items():
            evidence_count = len([item for item in evaluation.evidence if item.dimension == dimension_name])
            released_budget += plan.update_after_evaluation(
                dimension_name=dimension_name,
                coverage=coverage.get(dimension_name, 0.0),
                evidence_count=evidence_count,
            )
            if score < self.weak_score_threshold and evaluation.missing_points:
                self._increase_follow_up_budget(plan, dimension_name)
            if score >= self.high_score_threshold and coverage.get(dimension_name, 0.0) >= 0.55:
                self._complete_dimension_early(plan, dimension_name, coverage)
        return released_budget

    def _increase_follow_up_budget(self, plan: InterviewPlan, dimension_name: str) -> None:
        for item in plan.dimensions:
            if item.name == dimension_name and not item.completed:
                item.follow_up_budget = max(item.follow_up_budget, 1)
                return

    def _complete_dimension_early(
        self,
        plan: InterviewPlan,
        dimension_name: str,
        coverage: dict[str, float],
    ) -> None:
        plan.update_after_evaluation(
            dimension_name=dimension_name,
            coverage=max(coverage.get(dimension_name, 0.0), 0.75),
            evidence_count=0,
        )
