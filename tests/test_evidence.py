from __future__ import annotations

import asyncio

from conftest import make_mock_runtime


def test_evidence_contains_skill_and_polarity():
    asyncio.run(_case())


async def _case():
    runtime = make_mock_runtime()
    board = await runtime.start_session("evidence")
    board = await runtime.run_until_waiting_or_done(board.session_id)
    await runtime.receive_answer(board.session_id, "我会用 Cache Aside，删除缓存失败后通过消息队列补偿和重试。")
    board = await runtime.run_until_waiting_or_done(board.session_id)

    assert board.evidence
    assert board.evidence[0].polarity in {"positive", "uncertain"}
    assert board.evidence[0].source_question_id
