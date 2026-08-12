from __future__ import annotations

import asyncio

from interview_agent_runtime.context import EvaluationAgentContext, QuestionAgentContext, ReportAgentContext
from interview_agent_runtime.runtime import InterviewRuntime, InterviewStage
from interview_agent_runtime.context import ExecutionContext


def test_question_context_projects_recent_questions_not_full_evaluations():
    asyncio.run(_question_case())


async def _question_case():
    runtime = InterviewRuntime()
    board = await runtime.start_session("context-question")
    board = await runtime.run_until_waiting_or_done(board.session_id)
    agent = runtime.agent_registry.resolve(InterviewStage.NEXT_QUESTION)
    skill = runtime.skill_registry.resolve(agent.required_skill(board))
    visible = runtime.tool_policy.authorize(agent.name, skill)
    context = runtime.context_builder.build(
        agent.name,
        board,
        ExecutionContext(board.session_id, InterviewStage.NEXT_QUESTION, agent.name, skill.name, visible, skill.max_tokens, skill.timeout, skill.retry),
    )

    assert isinstance(context, QuestionAgentContext)
    assert context.current_plan is not None
    assert context.recent_questions
    assert not hasattr(context, "evaluations")
    assert not hasattr(context, "report")


def test_evaluator_context_is_current_turn_only():
    asyncio.run(_evaluation_case())


async def _evaluation_case():
    runtime = InterviewRuntime()
    board = await runtime.start_session("context-eval")
    board = await runtime.run_until_waiting_or_done(board.session_id)
    await runtime.receive_answer(board.session_id, "用缓存。")
    board = await runtime.load_context(board.session_id)
    agent = runtime.agent_registry.resolve(InterviewStage.EVALUATING)
    skill = runtime.skill_registry.resolve(agent.required_skill(board))
    visible = runtime.tool_policy.authorize(agent.name, skill)
    context = runtime.context_builder.build(
        agent.name,
        board,
        ExecutionContext(board.session_id, InterviewStage.EVALUATING, agent.name, skill.name, visible, skill.max_tokens, skill.timeout, skill.retry),
    )

    assert isinstance(context, EvaluationAgentContext)
    assert context.current_question is not None
    assert context.current_answer is not None
    assert context.expected_points
    assert not hasattr(context, "candidate_profile")
    assert not hasattr(context, "current_plan")


def test_report_context_contains_summaries_not_raw_answers():
    runtime = InterviewRuntime()
    board = asyncio.run(runtime.start_session("context-report"))
    agent = runtime.agent_registry.resolve(InterviewStage.REPORTING)
    skill = runtime.skill_registry.resolve(agent.required_skill(board))
    visible = runtime.tool_policy.authorize(agent.name, skill)
    context = runtime.context_builder.build(
        agent.name,
        board,
        ExecutionContext(board.session_id, InterviewStage.REPORTING, agent.name, skill.name, visible, skill.max_tokens, skill.timeout, skill.retry),
    )

    assert isinstance(context, ReportAgentContext)
    assert not hasattr(context, "answers")
    assert not hasattr(context, "question_history")
