from __future__ import annotations

import asyncio

from interview_agent_runtime.context import AgentContextBuilder, ContextBudget
from conftest import make_mock_runtime
from interview_agent_runtime.runtime import InterviewStage
from interview_agent_runtime.context import ExecutionContext


def test_context_budget_limits_recent_questions():
    asyncio.run(_case())


async def _case():
    runtime = make_mock_runtime(context_builder=AgentContextBuilder(ContextBudget(max_recent_questions=1)))
    board = await runtime.start_session("budget")
    board = await runtime.run_until_waiting_or_done(board.session_id)
    await runtime.receive_answer(board.session_id, "用缓存。")
    board = await runtime.run_until_waiting_or_done(board.session_id)
    agent = runtime.agent_registry.resolve(InterviewStage.NEXT_QUESTION)
    skill = runtime.skill_registry.resolve(agent.required_skill(board))
    visible = runtime.tool_policy.authorize(agent.name, skill)
    context = runtime.context_builder.build(
        agent.name,
        board,
        ExecutionContext(board.session_id, InterviewStage.NEXT_QUESTION, agent.name, skill.name, visible, skill.max_tokens, skill.timeout, skill.retry),
    )

    assert len(context.recent_questions) <= 1
