from __future__ import annotations

import asyncio

from interview_agent_runtime.artifacts import FollowUpDecisionArtifact
from conftest import make_mock_runtime
from interview_agent_runtime.runtime import InterviewStage


def test_evaluator_outputs_evaluation_and_followup_agent_outputs_decision():
    asyncio.run(_case())


async def _case():
    runtime = make_mock_runtime()
    board = await runtime.start_session("separation")
    board = await runtime.run_until_waiting_or_done(board.session_id)
    await runtime.receive_answer(board.session_id, "用缓存。")
    evaluation_step = await runtime.run_step(board.session_id)

    assert evaluation_step.previous_stage == InterviewStage.EVALUATING
    assert evaluation_step.artifact.kind == "evaluation"

    decision_step = await runtime.run_step(board.session_id)
    assert decision_step.previous_stage == InterviewStage.DECISION
    assert isinstance(decision_step.artifact, FollowUpDecisionArtifact)


def test_evaluator_does_not_decide_followup():
    from interview_agent_runtime.artifacts import EvaluationArtifact

    artifact = EvaluationArtifact(
        owner="EvaluatorAgent",
        question_id="q1",
        answer_id="a1",
        score=60,
        dimension_scores={"Redis": 60},
        evidence=[],
        missing_points=["删除缓存失败补偿"],
    )

    assert not hasattr(artifact, "need_follow_up")
    assert not hasattr(artifact, "follow_up_target")
