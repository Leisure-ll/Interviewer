from __future__ import annotations

import asyncio

from interview_agent_runtime.runtime import InterviewRuntime, InterviewStage


def test_runtime_enters_next_dimension_when_current_dimension_sufficient():
    asyncio.run(_case())


async def _case():
    runtime = InterviewRuntime()
    board = await runtime.start_session("dimension-transition")
    board = await runtime.run_until_waiting_or_done(board.session_id)
    await runtime.receive_answer(board.session_id, "用缓存。")
    board = await runtime.run_until_waiting_or_done(board.session_id)
    await runtime.receive_answer(board.session_id, "Cache Aside，删除缓存失败用消息队列补偿、重试、监控告警。")

    step = await runtime.run_step(board.session_id)
    while step.current_stage not in {InterviewStage.NEXT_DIMENSION, InterviewStage.LISTENING}:
        step = await runtime.run_step(board.session_id)

    assert step.current_stage in {InterviewStage.NEXT_DIMENSION, InterviewStage.LISTENING}
