from __future__ import annotations

import asyncio

from conftest import make_mock_runtime


def test_planner_agent_creates_interview_plan_from_profiles():
    asyncio.run(_case())


async def _case():
    runtime = make_mock_runtime()
    board = await runtime.start_session("planner")
    await runtime.run_step(board.session_id)
    await runtime.run_step(board.session_id)
    await runtime.run_step(board.session_id)
    board = await runtime.load_context(board.session_id)

    assert board.plan is not None
    assert board.plan.total_question_budget >= 2
    assert board.plan.dimensions[0].coverage_target > 0
