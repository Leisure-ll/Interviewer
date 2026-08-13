from __future__ import annotations

from typing import Any

from interview_agent_runtime.tools import Tool, ToolContext, ToolRegistry, ToolSpec


async def retrieve_resume(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    provided = context.blackboard.session_inputs.get("resume", {})
    if provided:
        data = dict(provided)
        data.setdefault("resume_id", "provided-resume")
        data.setdefault("candidate_id", context.blackboard.session_inputs.get("candidate_id") or context.session_id)
        return data
    return {
        "resume_id": "mock-resume",
        "candidate_id": context.session_id,
        "years_of_experience": 3.0,
        "skills": ["Java", "Redis", "RAG", "LLM Workflow"],
        "strengths": ["Java 后端", "Redis 缓存", "Agent Runtime"],
        "possible_weaknesses": ["系统设计深度需要验证"],
        "resume_keywords": ["Java", "Redis", "Qdrant", "Agent"],
    }


async def retrieve_jd(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    provided = context.blackboard.session_inputs.get("jd", {})
    if provided:
        return dict(provided)
    return {
        "position": "Java Backend Agent Intern",
        "seniority": "intern",
        "required_skills": ["Java Backend"],
        "preferred_skills": ["Agent Engineering", "Redis"],
        "responsibilities": ["参与 AI 面试系统后端和 Agent 能力建设"],
        "dimensions": ["Java Backend", "Agent Engineering"],
        "keywords": ["Java", "Redis", "Agent", "RAG"],
    }


async def search_question_bank(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    dimension = args.get("dimension")
    questions = [
        {
            "question_id": "q-java-redis-1",
            "title": "请说明 Redis 缓存一致性在后端系统中如何设计。",
            "dimension": "Java Backend",
            "difficulty": "medium",
            "reference_answer": "Cache Aside、删除缓存失败重试、延迟双删、消息队列补偿。",
            "expected_points": ["Cache Aside", "失败补偿策略", "监控告警"],
            "related_skills": ["Redis", "缓存一致性"],
        },
        {
            "question_id": "q-java-kafka-1",
            "title": "如果订单事件通过消息队列异步处理，你会如何保证消费可靠性？",
            "dimension": "Java Backend",
            "difficulty": "hard",
            "reference_answer": "幂等、重试、死信队列、事务消息、监控告警。",
            "expected_points": ["幂等", "重试", "死信队列", "监控"],
            "related_skills": ["Kafka", "消息队列"],
        },
        {
            "question_id": "q-agent-runtime-1",
            "title": "如果让你设计一个面试 Agent，你会如何拆分状态、工具和模型调用？",
            "dimension": "Agent Engineering",
            "difficulty": "medium",
            "reference_answer": "FSM、Artifact、Blackboard、Tool Policy、Checkpoint。",
            "expected_points": ["状态机", "Artifact", "Blackboard", "工具权限", "Checkpoint"],
            "related_skills": ["Agent Runtime", "Tool Governance"],
        },
        {
            "question_id": "q-system-design-1",
            "title": "请设计一个高并发面试会话服务，说明限流、降级和状态恢复方案。",
            "dimension": "System Design",
            "difficulty": "hard",
            "reference_answer": "限流、降级、异步解耦、状态持久化、幂等恢复。",
            "expected_points": ["限流", "降级", "状态恢复", "幂等"],
            "related_skills": ["System Design"],
        },
    ]
    if dimension:
        questions = [item for item in questions if item["dimension"] == dimension]
    return {
        "questions": questions[: args.get("limit", 5)]
    }


async def retrieve_knowledge(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    return {"items": []}


async def retrieve_rubric(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    return {"rubric": "score by evidence, correctness, depth, and clarity"}


async def semantic_match(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    return {"score": 0.75}


async def evaluation_history(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    return {"evaluations": [e.score for e in context.blackboard.evaluations]}


async def aggregate_evidence(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    return {"evidence_count": len(context.blackboard.evidence)}


def build_default_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    read_tools = [
        ("resume.retrieve", "Retrieve parsed resume profile.", retrieve_resume),
        ("jd.retrieve", "Retrieve JD and competency dimensions.", retrieve_jd),
        ("question_bank.search", "Search Qdrant-backed question bank.", search_question_bank),
        ("knowledge.retrieve", "Retrieve domain knowledge.", retrieve_knowledge),
        ("rubric.retrieve", "Retrieve scoring rubric.", retrieve_rubric),
        ("answer.semantic_match", "Match answer against rubric/reference.", semantic_match),
        ("evaluation.history", "Read evaluation history.", evaluation_history),
        ("evidence.aggregate", "Aggregate evidence.", aggregate_evidence),
    ]
    for name, description, handler in read_tools:
        registry.register(
            Tool(
                spec=ToolSpec(
                    name=name,
                    description=description,
                    parallel_safe=True,
                ),
                handler=handler,
            )
        )
    return registry


