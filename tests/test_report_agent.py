from __future__ import annotations

import asyncio

from interview_agent_runtime.runtime import InterviewRuntime, InterviewStage


def test_report_has_role_match_and_key_evidence():
    asyncio.run(_case())


async def _case():
    runtime = InterviewRuntime()
    board = await runtime.start_session("report")
    answers = [
        "用缓存。",
        "Cache Aside，删除缓存失败后消息队列补偿、重试、监控告警。",
        "状态机控制，Artifact 写 Blackboard，工具权限控制，checkpoint 恢复。",
        "项目中我负责缓存优化，描述场景、约束、方案、权衡、结果。",
    ]
    index = 0
    while True:
        board = await runtime.run_until_waiting_or_done(board.session_id)
        if board.current_stage == InterviewStage.LISTENING:
            await runtime.receive_answer(board.session_id, answers[min(index, len(answers) - 1)])
            index += 1
            continue
        break

    assert board.report is not None
    assert board.report.role_match_score > 0
    assert board.report.key_evidence
    assert board.report.hiring_recommendation
