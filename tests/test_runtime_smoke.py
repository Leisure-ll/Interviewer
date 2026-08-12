from __future__ import annotations

import pytest
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from interview_agent_runtime.runtime import InterviewRuntime, InterviewStage


def test_runtime_runs_question_answer_followup_and_report():
    asyncio.run(_runtime_smoke())


async def _runtime_smoke():
    runtime = InterviewRuntime()
    board = await runtime.start_session("s1")

    board = await runtime.run_until_waiting_or_done(board.session_id)
    assert board.current_stage == InterviewStage.LISTENING
    assert board.current_question is not None
    assert board.current_question.question_id == "q-java-redis-1"

    await runtime.receive_answer(board.session_id, "用缓存")
    board = await runtime.run_until_waiting_or_done(board.session_id)
    assert board.current_stage == InterviewStage.LISTENING
    assert board.current_question is not None
    assert board.current_question.is_follow_up is True

    await runtime.receive_answer(board.session_id, "我会使用 Cache Aside，删除缓存失败时通过消息队列补偿并监控重试。")
    board = await runtime.run_until_waiting_or_done(board.session_id)
    assert board.current_stage == InterviewStage.LISTENING
    assert board.current_question is not None
    assert board.current_question.question_id == "q-agent-runtime-1"

    await runtime.receive_answer(board.session_id, "我会用状态机控制流程，用 artifact 写入 blackboard，再由 guard 决定迁移。")
    board = await runtime.run_until_waiting_or_done(board.session_id)
    assert board.current_stage == InterviewStage.FINISHED
    assert board.report is not None
    assert board.evidence


def test_tool_policy_denies_undeclared_tool():
    asyncio.run(_tool_policy_smoke())


async def _tool_policy_smoke():
    runtime = InterviewRuntime()
    board = await runtime.start_session("s2")
    board = await runtime.run_until_waiting_or_done(board.session_id)
    assert board.current_stage == InterviewStage.LISTENING

    # QuestionAgent's visible tools do not include evaluation.history.
    agent = runtime.agent_registry.resolve(InterviewStage.NEXT_QUESTION)
    skill = runtime.skill_registry.resolve(agent.required_skill(board))
    visible = runtime.tool_policy.authorize(agent.name, skill)
    assert "evaluation.history" not in visible
