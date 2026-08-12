from __future__ import annotations

import asyncio
from typing import Any

from conftest import make_mock_runtime
from interview_agent_runtime.tools import Tool, ToolContext


async def empty_question_bank(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    return {"questions": []}


def test_question_generation_falls_back_when_bank_empty():
    asyncio.run(_case())


async def _case():
    runtime = make_mock_runtime()
    runtime.tool_registry.register(Tool("question_bank.search", "empty", empty_question_bank))
    board = await runtime.start_session("question-fallback")
    board = await runtime.run_until_waiting_or_done(board.session_id)

    assert board.current_question is not None
    assert board.current_question.source == "runtime_fallback"
    assert "Java Backend" in board.current_question.title
