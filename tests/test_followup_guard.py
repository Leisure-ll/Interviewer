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
