from __future__ import annotations

import asyncio

from conftest import make_mock_runtime


def test_profile_agent_builds_candidate_and_position_profiles():
    asyncio.run(_case())


async def _case():
    runtime = make_mock_runtime()
    board = await runtime.start_session("profile")
    await runtime.run_step(board.session_id)
    await runtime.run_step(board.session_id)
    board = await runtime.load_context(board.session_id)

    assert board.candidate is not None
    assert "Redis" in board.candidate.skills
    assert board.position_profile is not None
    assert "Java Backend" in board.position_profile.competency_dimensions
