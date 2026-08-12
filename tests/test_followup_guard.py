from __future__ import annotations

from interview_agent_runtime.artifacts import FollowUpDecisionArtifact
from interview_agent_runtime.blackboard import InterviewBlackboard
from interview_agent_runtime.runtime.state_machine import TransitionGuard


def test_followup_guard_denies_duplicate_normalized_target():
    board = InterviewBlackboard(session_id="guard")
    board.follow_up_budget = 1
    board.followed_targets.add("具体实现细节")
    decision = FollowUpDecisionArtifact(
        owner="FollowUpAgent",
        question_id="q1",
        need_follow_up=True,
        confidence=0.9,
        target="具体 实现 细节",
    )

    assert TransitionGuard().allow_follow_up(board, decision) is False


def test_followup_guard_accepts_valid_decision():
    board = InterviewBlackboard(session_id="guard-valid")
    board.follow_up_budget = 1
    board.current_dimension = "Redis"
    from interview_agent_runtime.domain import InterviewDimension, InterviewPlan
    from interview_agent_runtime.artifacts import InterviewPlanArtifact

    board.publish(
        InterviewPlanArtifact(
            owner="PlannerAgent",
            plan=InterviewPlan(
                dimensions=[InterviewDimension("Redis", 1.0, "advanced", 1, 1, 0.8, "hard")],
                total_question_budget=1,
                total_follow_up_budget=1,
                estimated_duration_minutes=5,
            ),
        )
    )
    decision = FollowUpDecisionArtifact(
        owner="FollowUpAgent",
        question_id="q1",
        need_follow_up=True,
        confidence=0.9,
        target="删除缓存失败补偿",
    )

    assert TransitionGuard().allow_follow_up(board, decision) is True


def test_followup_guard_rejects_low_confidence():
    board = InterviewBlackboard(session_id="guard-low")
    board.follow_up_budget = 1
    decision = FollowUpDecisionArtifact(
        owner="FollowUpAgent",
        question_id="q1",
        need_follow_up=True,
        confidence=0.3,
        target="删除缓存失败补偿",
    )

    assert TransitionGuard().allow_follow_up(board, decision) is False


def test_followup_guard_rejects_budget_exhausted():
    board = InterviewBlackboard(session_id="guard-budget")
    board.follow_up_budget = 0
    decision = FollowUpDecisionArtifact(
        owner="FollowUpAgent",
        question_id="q1",
        need_follow_up=True,
        confidence=0.9,
        target="删除缓存失败补偿",
    )

    assert TransitionGuard().allow_follow_up(board, decision) is False
