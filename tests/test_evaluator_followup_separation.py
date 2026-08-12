from __future__ import annotations

import asyncio

from interview_agent_runtime.artifacts import FollowUpDecisionArtifact
from interview_agent_runtime.runtime import InterviewRuntime, InterviewStage


def test_evaluator_outputs_evaluation_and_followup_agent_outputs_decision():
    asyncio.run(_case())


async def _case():
    runtime = InterviewRuntime()
    board = await runtime.start_session("separation")
    board = await runtime.run_until_waiting_or_done(board.session_id)
    await runtime.receive_answer(board.session_id, "用缓存。")
    evaluation_step = await runtime.run_step(board.session_id)

    assert evaluation_step.previous_stage == InterviewStage.EVALUATING
    assert evaluation_step.artifact.kind == "evaluation"

    decision_step = await runtime.run_step(board.session_id)
    assert decision_step.previous_stage == InterviewStage.DECISION
    assert isinstance(decision_step.artifact, FollowUpDecisionArtifact)
