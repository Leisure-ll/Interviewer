from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from interview_agent_runtime.application import InterviewApplicationService
from interview_agent_runtime.blackboard import InterviewBlackboard
from interview_agent_runtime.harness import InterviewHarness
from interview_agent_runtime.memory import InterviewMemorySnapshot, InMemorySessionMemory
from interview_agent_runtime.messages import AgentMessage
from interview_agent_runtime.providers import FakeLLMProvider
from interview_agent_runtime.runtime import AgentLoop, AgentRunRequest, InterviewStage
from interview_agent_runtime.tools import (
    FakeMCPClient,
    MCPToolAdapter,
    MCPToolDefinition,
    ToolContext,
    ToolExecutor,
    ToolPolicy,
    ToolRegistry,
)


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
    print_memory_snapshot(board)
    await print_trace_summary(harness, board.runtime_metadata.trace_id)
    await print_mcp_tool_calling_example()


def print_runtime_events(service: InterviewApplicationService, start: int) -> None:
    events = service.runtime.event_bus.events[start:]
    for event in events:
        if event.type.value == "AGENT_LOOP_STARTED":
            print(
                "[LOOP] "
                f"AGENT_LOOP_STARTED agent={event.metadata.get('agent')} "
                f"skill={event.metadata.get('skill')}"
            )
        elif event.type.value == "LLM_REQUESTED":
            print(
                "[LOOP] "
                f"LLM_REQUESTED agent={event.metadata.get('agent')} "
                f"skill={event.metadata.get('skill')} "
                f"round={event.metadata.get('round')} "
                f"tool_count={event.metadata.get('tool_count')}"
            )
        elif event.type.value == "LLM_RESPONDED":
            print(
                "[LOOP] "
                f"LLM_RESPONDED agent={event.metadata.get('agent')} "
                f"skill={event.metadata.get('skill')} "
                f"round={event.metadata.get('round')} "
                f"finish_reason={event.metadata.get('finish_reason')}"
            )
        elif event.type.value == "TOOL_CALLED":
            print(
                "[LOOP] "
                f"TOOL_CALLED agent={event.metadata.get('agent')} "
                f"skill={event.metadata.get('skill')} "
                f"round={event.metadata.get('round')} "
                f"tool={event.metadata.get('tool')}"
            )
        elif event.type.value == "TOOL_SUCCEEDED":
            print(
                "[LOOP] "
                f"TOOL_SUCCEEDED agent={event.metadata.get('agent')} "
                f"skill={event.metadata.get('skill')} "
                f"round={event.metadata.get('round')} "
                f"tool={event.metadata.get('tool')}"
            )
        elif event.type.value == "TOOL_FAILED":
            print(
                "[LOOP] "
                f"TOOL_FAILED agent={event.metadata.get('agent')} "
                f"skill={event.metadata.get('skill')} "
                f"round={event.metadata.get('round')} "
                f"tool={event.metadata.get('tool')}"
            )
        elif event.type.value == "AGENT_LOOP_FINISHED":
            print(
                "[LOOP] "
                f"AGENT_LOOP_FINISHED agent={event.metadata.get('agent')} "
                f"skill={event.metadata.get('skill')} "
                f"rounds={event.metadata.get('rounds')} "
                f"tool_calls={event.metadata.get('tool_calls')}"
            )
        elif event.type.value == "AGENT_LOOP_STOPPED":
            print(
                "[LOOP] "
                f"AGENT_LOOP_STOPPED agent={event.metadata.get('agent')} "
                f"skill={event.metadata.get('skill')} "
                f"reason={event.metadata.get('stop_reason')}"
            )
        elif event.type.value == "AGENT_STARTED":
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


def print_memory_snapshot(board) -> None:
    snapshot = InterviewMemorySnapshot.from_blackboard(board)
    print("\n=== Memory Context Example ===")
    print("Interaction Memory: ProfileAgent recent assistant/tool messages in SessionMemory")
    print("Domain Snapshot:")
    print(f"current_dimension={snapshot.current_dimension or '-'}")
    print(f"verified_skills={snapshot.verified_skills}")
    print(f"weak_skills={snapshot.weak_skills}")
    print(f"uncertain_skills={snapshot.uncertain_skills}")
    print(f"dimension_coverage={snapshot.dimension_coverage}")
    print(f"unresolved_gaps={snapshot.unresolved_gaps[:3]}")


async def print_trace_summary(harness: InterviewHarness, trace_id: str) -> None:
    print("\n=== Trace Example ===")
    print(trace_id)
    trace_store = getattr(harness, "trace_store", None)
    trace = await trace_store.load(trace_id) if trace_store is not None else None
    if trace is None:
        print("trace unavailable")
        return
    for span in trace.spans[:8]:
        print(
            f"- {span.kind} {span.span_id} parent={span.parent_span_id or '-'} "
            f"name={span.name} status={span.status}"
        )


async def print_mcp_tool_calling_example() -> None:
    print("\n=== MCP Tool Calling Example ===")
    client = FakeMCPClient(
        tools=[MCPToolDefinition("knowledge.search", "Search knowledge")],
        responses={"knowledge.search": {"items": ["Cache Aside"]}},
    )
    registry = ToolRegistry()
    await MCPToolAdapter(client).load_tools(registry)
    provider = FakeLLMProvider(
        responses=[
            {
                "tool_calls": [
                    {
                        "id": "mcp_demo_call",
                        "name": "mcp.knowledge.search",
                        "arguments": {"query": "cache"},
                    }
                ]
            },
            {"content": '{"done": true}'},
        ]
    )
    result = await AgentLoop(provider, InMemorySessionMemory()).run(
        AgentRunRequest(
            session_id="demo-mcp",
            agent_name="QuestionAgent",
            skill_name="question-generation",
            initial_messages=[AgentMessage.system("system"), AgentMessage.user("search knowledge")],
            visible_tools={"mcp.knowledge.search"},
            tool_executor=ToolExecutor(
                registry,
                ToolPolicy({"QuestionAgent": {"mcp.knowledge.search"}}),
            ),
            tool_context=ToolContext(
                "demo-mcp",
                "QuestionAgent",
                "question-generation",
                InterviewBlackboard("demo-mcp"),
            ),
        )
    )
    print("QuestionAgent / AgentLoop")
    print("assistant -> mcp.knowledge.search")
    print(f"MCPToolAdapter -> FakeMCPClient calls={client.calls}")
    print(f"stop_reason={result.stop_reason}")


if __name__ == "__main__":
    asyncio.run(main())
