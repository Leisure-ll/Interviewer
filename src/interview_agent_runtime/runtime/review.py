from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from interview_agent_runtime.artifacts import InterviewReportArtifact
from interview_agent_runtime.blackboard import InterviewBlackboard


class ReviewDecisionType(str, Enum):
    AUTO_COMPLETE = "auto_complete"
    REQUIRE_HUMAN_REVIEW = "require_human_review"


class ReviewStatus(str, Enum):
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass
class ReviewDecision:
    decision: ReviewDecisionType
    reasons: list[str]
    confidence: Optional[float] = None

    @property
    def requires_human_review(self) -> bool:
        return self.decision == ReviewDecisionType.REQUIRE_HUMAN_REVIEW

    @property
    def status(self) -> ReviewStatus:
        return ReviewStatus.PENDING if self.requires_human_review else ReviewStatus.NOT_REQUIRED


@dataclass
class HumanReviewPolicy:
    """Deterministic gate for high-impact report completion."""

    min_evidence_count: int = 1
    min_dimension_coverage: float = 0.5
    min_report_confidence: float = 0.65
    require_review_for_uncertainty: bool = False

    def evaluate(
        self,
        blackboard: InterviewBlackboard,
        report: InterviewReportArtifact,
    ) -> ReviewDecision:
        reasons: list[str] = []
        confidence = report.confidence
        if confidence < self.min_report_confidence:
            reasons.append("report confidence below review threshold")
        if len(blackboard.evidence) < self.min_evidence_count:
            reasons.append("evidence coverage is insufficient")
        coverages = list(blackboard.dimension_coverage.values())
        if coverages and min(coverages) < self.min_dimension_coverage:
            reasons.append("at least one dimension is below coverage threshold")
        if self.require_review_for_uncertainty and (
            report.insufficient_evidence_areas
            or blackboard.capability_profile.uncertain_skills
        ):
            reasons.append("important capability remains uncertain")
        if reasons:
            return ReviewDecision(
                ReviewDecisionType.REQUIRE_HUMAN_REVIEW,
                reasons,
                confidence=confidence,
            )
        return ReviewDecision(
            ReviewDecisionType.AUTO_COMPLETE,
            [],
            confidence=confidence,
        )


__all__ = [
    "HumanReviewPolicy",
    "ReviewDecision",
    "ReviewDecisionType",
    "ReviewStatus",
]
