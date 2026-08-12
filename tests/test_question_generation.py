from __future__ import annotations

import asyncio

from conftest import make_mock_runtime
from interview_agent_runtime.runtime import InterviewStage


def test_question_generation_uses_plan_dimension_and_bank():
    asyncio.run(_case())


async def _case():
    runtime = make_mock_runtime()
    board = await runtime.start_session("question-generation")
    board = await runtime.run_until_waiting_or_done(board.session_id)

    assert board.current_stage == InterviewStage.LISTENING
    assert board.current_question is not None
    assert board.current_question.dimension == "Java Backend"
    assert board.current_question.source == "question_bank"
