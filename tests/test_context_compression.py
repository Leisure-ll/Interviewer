from __future__ import annotations

import asyncio

from interview_agent_runtime.context import CapabilityContextCompressor
from conftest import make_mock_runtime


def test_capability_context_compressor_keeps_capability_state_not_chat_story():
    asyncio.run(_case())


async def _case():
    runtime = make_mock_runtime()
    board = await runtime.start_session("compress")
    board = await runtime.run_until_waiting_or_done(board.session_id)
    await runtime.receive_answer(board.session_id, "用缓存。")
    board = await runtime.run_until_waiting_or_done(board.session_id)
    summary = CapabilityContextCompressor(runtime.context_builder).compress(board)

    assert "dimension_coverage" in summary
    assert "unresolved_gaps" in summary
    assert "estimated_tokens" in summary
    assert "answers" not in summary
