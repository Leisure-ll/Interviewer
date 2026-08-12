from __future__ import annotations

import asyncio

from interview_agent_runtime.runtime import InterviewRuntime, InterviewStage


def test_evaluation_extracts_evidence_and_missing_points():
    asyncio.run(_case())


async def _case():
    runtime = InterviewRuntime()
    board = await runtime.start_session("evaluation")
    board = await runtime.run_until_waiting_or_done(board.session_id)
    await runtime.receive_answer(board.session_id, "用缓存")
    board = await runtime.run_until_waiting_or_done(board.session_id)

    assert board.current_stage == InterviewStage.LISTENING
    assert board.evaluations
    assert board.evidence
    assert board.evaluations[-1].missing_points
    assert board.current_question is not None
    assert board.current_question.is_follow_up
