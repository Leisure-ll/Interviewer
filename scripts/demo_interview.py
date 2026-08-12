from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from interview_agent_runtime.application import InterviewApplicationService
from interview_agent_runtime.harness import InterviewHarness
from interview_agent_runtime.runtime import InterviewStage


RESUME = {
    "resume_id": "demo-resume",
    "skills": ["Java", "Redis", "Agent Engineering", "System Design"],
    "resume_keywords": ["Java", "Redis", "Agent", "高并发", "秒杀"],
    "years_of_experience": 2.0,
    "strengths": ["Java 后端", "Redis 缓存", "Agent Runtime"],
    "potential_gaps": ["系统设计深度", "线上故障处理"],
}

JD = {
    "position": "Java Backend Agent Intern",
    "seniority": "intern",
    "required_skills": ["Java Backend"],
    "preferred_skills": ["Agent Engineering", "Redis", "System Design"],
    "responsibilities": ["参与 AI 面试系统后端开发", "建设 Agent Runtime 和 RAG 能力"],
    "dimensions": ["Java Backend", "Agent Engineering", "System Design"],
    "keywords": ["Java", "Redis", "Agent", "RAG", "高并发"],
}


def choose_answer(question_text: str, dimension: str, is_follow_up: bool) -> str:
    if is_follow_up and "具体实现细节" in question_text:
        return "我会使用 Cache Aside，更新数据库后删除缓存；如果删除失败，通过消息队列补偿、重试，并加监控告警。"
    if dimension == "Java Backend":
        return "用缓存。"
    if dimension == "Agent Engineering":
        return "我会用状态机控制流程，Agent 只产出 Artifact 写入 Blackboard，工具调用通过权限控制，异常时 fallback，checkpoint 支持恢复。"
    if dimension == "System Design":
        return "我会做限流和降级，用异步队列解耦核心链路，并把会话状态持久化，恢复时保证幂等。"
    if dimension == "Project Experience":
        return "项目中我负责缓存优化和 Agent 状态恢复，先分析场景和约束，再设计方案、权衡一致性和延迟，最后用监控验证结果。"
    return "我会结合场景、约束、方案、权衡和结果完整说明。"


async def main() -> None:
    harness = InterviewHarness.from_config()
    print(f"[HARNESS] boot mode={harness.config.mode}")
    service = InterviewApplicationService(harness=harness)
    status = await service.start_interview(
        candidate_id="demo-candidate",
        resume=RESUME,
        jd=JD,
        session_id="demo-java-agent-candidate",
    )

    board = await service.runtime.load_context(status.session_id)
    print_runtime_events(service, start=0)
    print("[STATE] PROFILE_ANALYSIS -> INTERVIEW_PLANNING -> QUESTION_PREPARING")
    print("\nCandidate Profile:")
    print(f"Skills: {', '.join(board.candidate.skills if board.candidate else [])}")
    print(f"Experience: {board.candidate.years_of_experience if board.candidate else '-'} years")

    print("\nInterview Plan:")
    for item in board.plan.dimensions:
        print(
            f"- {item.name:18} weight={item.weight:.2f} difficulty={item.difficulty} "
            f"questions={item.question_budget} followups={item.follow_up_budget}"
        )

    turn = 1
    while status.stage == InterviewStage.LISTENING:
        question = status.current_question
        print(f"\n[STATE] QUESTIONING -> LISTENING")
        print(f"[QUESTION {turn}] {question.dimension} / {question.difficulty} / {question.source}")
        print(question.title)

        answer = choose_answer(question.title, question.dimension, question.is_follow_up)
        print("\n[ANSWER]")
        print(answer)

        previous_stage = status.stage
        event_start = len(service.runtime.event_bus.events)
        status = await service.submit_answer(status.session_id, answer)
        board = await service.runtime.load_context(status.session_id)
        evaluation = board.latest_evaluation
        decision = board.latest_follow_up_decision

        print("\n[EVALUATION]")
        print(f"Score: {evaluation.overall_score if evaluation else '-'}")
        if evaluation:
            print("Evidence:")
            for evidence in evaluation.evidence[:3]:
                print(f"- {evidence.polarity}: {evidence.claim}")
            print(f"Missing: {', '.join(evaluation.missing_points) or '-'}")
        print(f"Follow-up: {'YES' if decision and decision.need_follow_up else 'NO'}")
        print(f"[TRANSITION] {previous_stage.value} -> {status.stage.value}")
        print_runtime_events(service, start=event_start)
        turn += 1

    report = await service.get_report(status.session_id)
    if report is None:
        raise RuntimeError(f"Interview did not produce report: {status.stage.value}")

    print("\n=== Interview Report ===")
    print(f"Stage: {status.stage.value}")
    print(f"Overall Score: {report.overall_score}")
    print(f"Role Match Score: {report.role_match_score}")
    print(f"Role Match: {report.role_match}")
    print(f"Verified: {', '.join(report.verified_skills) or '-'}")
    print(f"Weak: {', '.join(report.weak_skills) or '-'}")
    print(f"Uncertain: {', '.join(report.insufficient_evidence_areas) or '-'}")
    print(f"Evidence Count: {len(report.evidence)}")
    print(f"Recommendation: {report.hiring_recommendation}")


def print_runtime_events(service: InterviewApplicationService, start: int) -> None:
    events = service.runtime.event_bus.events[start:]
    for event in events:
        if event.type.value == "AGENT_STARTED":
            print(
                "[AGENT] "
                f"{event.metadata.get('agent')} skill={event.metadata.get('skill')} "
                f"context={event.metadata.get('context_type')} "
                f"tools={event.metadata.get('authorized_tools')}"
            )
        elif event.type.value == "AGENT_FINISHED":
            print(
                "[ARTIFACT] "
                f"{event.metadata.get('agent')} -> {event.metadata.get('artifact')}"
            )
        elif event.type.value == "STATE_TRANSITIONED":
            print(
                "[EVENT] transition "
                f"{event.metadata.get('from')} -> {event.metadata.get('to')}"
            )
        elif event.type.value == "SESSION_STARTED":
            print(f"[EVENT] session started {event.session_id}")
        elif event.type.value == "QUESTION_ASKED":
            print("[EVENT] question asked; checkpoint saved")


if __name__ == "__main__":
    asyncio.run(main())
