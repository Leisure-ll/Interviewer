from __future__ import annotations

import asyncio

from conftest import make_mock_runtime
from interview_agent_runtime.runtime import InterviewStage


def test_full_java_agent_interview_flow_produces_evidence_driven_report():
    asyncio.run(_case())


async def _case():
    runtime = make_mock_runtime()
    board = await runtime.start_session("full-flow")
    answers = [
        "用缓存。",
        "我会用 Cache Aside，更新数据库后删除缓存，删除失败就发消息队列补偿，失败重试，并加监控告警。",
        "我会用状态机控制流程，用 Artifact 写入 Blackboard，工具调用要有权限控制，异常时 fallback，checkpoint 支持恢复。",
    ]
    index = 0
    while True:
        board = await runtime.run_until_waiting_or_done(board.session_id)
        if board.current_stage == InterviewStage.LISTENING:
            await runtime.receive_answer(board.session_id, answers[min(index, len(answers) - 1)])
            index += 1
            continue
        break

    assert board.current_stage == InterviewStage.FINISHED
    assert board.report is not None
    assert board.report.overall_score > 0
    assert board.report.evidence
    assert board.capability_profile.dimension_scores
    assert any(item.evidence_type in {"positive", "insufficient"} for item in board.evidence)
