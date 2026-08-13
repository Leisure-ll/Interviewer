from __future__ import annotations

import asyncio

from conftest import make_mock_runtime
from interview_agent_runtime.runtime import HumanReviewPolicy, InterviewStage


def test_runtime_waits_for_review_and_persists_human_decision():
    asyncio.run(_case())


async def _case():
    runtime = make_mock_runtime(
        human_review_policy=HumanReviewPolicy(
            min_evidence_count=999,
            min_report_confidence=0.99,
        )
    )
    board = await runtime.start_session("review-flow")
    answers = [
        "用缓存。",
        "Cache Aside，失败重试和消息队列补偿。",
        "用状态机、Artifact、Blackboard 和 checkpoint。",
    ]
    index = 0
    while True:
        board = await runtime.run_until_waiting_or_done(board.session_id)
        if board.current_stage != InterviewStage.LISTENING:
            break
        await runtime.receive_answer(board.session_id, answers[min(index, len(answers) - 1)])
        index += 1

    assert board.current_stage == InterviewStage.WAITING_HUMAN_REVIEW
    assert board.review_status == "pending"
    assert board.review_required

    approved = await runtime.submit_human_review(
        board.session_id,
        approved=True,
        reviewer="recruiter",
        reason="evidence reviewed",
    )
    assert approved.current_stage == InterviewStage.FINISHED
    restored = await runtime.load_context(board.session_id)
    assert restored.review_status == "approved"
    assert restored.review_reviewer == "recruiter"
