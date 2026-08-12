from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from interview_agent_runtime.runtime import InterviewRuntime, InterviewStage


ANSWERS = [
    "用缓存。",
    "我会使用 Cache Aside，更新数据库后删除缓存；如果删除失败，会通过消息队列补偿、重试，并加监控告警。",
    "我会用状态机控制流程，Agent 只产出 Artifact 写入 Blackboard，工具调用通过权限白名单控制，并用 checkpoint 做中断恢复。",
]


async def main() -> None:
    runtime = InterviewRuntime()
    board = await runtime.start_session("demo-java-agent-candidate")
    answer_index = 0

    while True:
        board = await runtime.run_until_waiting_or_done(board.session_id)
        if board.current_stage == InterviewStage.LISTENING:
            question = board.current_question
            print(f"\nQ[{question.dimension}]: {question.title}")
            answer = ANSWERS[min(answer_index, len(ANSWERS) - 1)]
            print(f"A: {answer}")
            answer_index += 1
            await runtime.receive_answer(board.session_id, answer)
            continue
        if board.current_stage in {InterviewStage.FINISHED, InterviewStage.FAILED}:
            break

    if board.report is None:
        raise RuntimeError(f"Interview did not produce report: {board.current_stage.value}")

    print("\n=== Interview Report ===")
    print(f"Stage: {board.current_stage.value}")
    print(f"Overall Score: {board.report.overall_score}")
    print(f"Role Match: {board.report.role_match}")
    print(f"Verified: {', '.join(board.report.verified_skills) or '-'}")
    print(f"Weak: {', '.join(board.report.weak_skills) or '-'}")
    print(f"Evidence Count: {len(board.report.evidence)}")
    print(f"Recommendation: {board.report.hiring_recommendation}")


if __name__ == "__main__":
    asyncio.run(main())
