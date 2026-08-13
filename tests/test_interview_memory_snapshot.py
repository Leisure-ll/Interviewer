from __future__ import annotations

import asyncio

from interview_agent_runtime.blackboard import InterviewBlackboard
from interview_agent_runtime.memory import InterviewMemorySnapshot


def test_interview_memory_snapshot_is_domain_state_not_transcript():
    asyncio.run(_case())


async def _case():
    board = InterviewBlackboard("snapshot")
    board.current_dimension = "Redis"
    board.capability_profile.verified_skills = ["Java"]
    board.capability_profile.uncertain_skills = ["Redis consistency"]
    board.capability_profile.dimension_scores = {"Redis": 78.0}
    board.capability_profile.dimension_coverage = {"Redis": 0.6}

    snapshot = InterviewMemorySnapshot.from_blackboard(board)

    assert snapshot.verified_skills == ["Java"]
    assert snapshot.uncertain_skills == ["Redis consistency"]
    assert snapshot.dimension_coverage == {"Redis": 0.6}
    assert snapshot.current_dimension == "Redis"
    assert "assistant" not in snapshot.to_dict()
