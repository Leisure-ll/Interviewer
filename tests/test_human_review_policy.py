from __future__ import annotations

from interview_agent_runtime.artifacts import Evidence, InterviewReportArtifact
from interview_agent_runtime.blackboard import InterviewBlackboard
from interview_agent_runtime.runtime import HumanReviewPolicy, ReviewDecisionType


def _report(confidence: float = 0.9, uncertain=None) -> InterviewReportArtifact:
    report = InterviewReportArtifact(
        owner="ReportAgent",
        overall_score=80,
        dimension_scores={"Java": 80},
        verified_skills=["Java"],
        weak_skills=[],
        evidence=[],
        insufficient_evidence_areas=uncertain or [],
    )
    report.confidence = confidence
    return report


def test_high_confidence_with_evidence_auto_completes():
    board = InterviewBlackboard("review-ok")
    board.evidence.append(
        Evidence(
            dimension="Java",
            claim="Cache Aside",
            source_answer_id="a1",
            quote_or_summary="Cache Aside",
            confidence=0.9,
        )
    )
    board.capability_profile.dimension_coverage["Java"] = 0.8

    decision = HumanReviewPolicy().evaluate(board, _report())

    assert decision.decision == ReviewDecisionType.AUTO_COMPLETE


def test_low_confidence_or_missing_evidence_requires_review():
    board = InterviewBlackboard("review-required")
    decision = HumanReviewPolicy(min_evidence_count=1).evaluate(
        board,
        _report(confidence=0.4),
    )

    assert decision.decision == ReviewDecisionType.REQUIRE_HUMAN_REVIEW
    assert decision.reasons
