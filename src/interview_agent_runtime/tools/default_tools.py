from __future__ import annotations

from typing import Any

from interview_agent_runtime.tools import Tool, ToolContext, ToolRegistry


async def retrieve_resume(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    return {
        "resume_id": "mock-resume",
        "skills": ["Java", "Redis", "RAG", "LLM Workflow"],
    }


async def retrieve_jd(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    return {
        "position": "Java Backend Agent Intern",
        "dimensions": ["Java Backend", "Agent Engineering"],
    }


async def search_question_bank(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    return {
        "questions": [
            {
                "question_id": "q-java-redis-1",
                "title": "请说明 Redis 缓存一致性在后端系统中如何设计。",
                "dimension": "Java Backend",
                "difficulty": "medium",
                "reference_answer": "Cache Aside、删除缓存失败重试、延迟双删、消息队列补偿。",
            },
            {
                "question_id": "q-agent-runtime-1",
                "title": "如果让你设计一个面试 Agent，你会如何拆分状态、工具和模型调用？",
                "dimension": "Agent Engineering",
                "difficulty": "medium",
                "reference_answer": "FSM、Artifact、Blackboard、Tool Policy、Checkpoint。",
            },
        ]
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
    registry.register(Tool("resume.retrieve", "Retrieve parsed resume profile.", retrieve_resume))
    registry.register(Tool("jd.retrieve", "Retrieve JD and competency dimensions.", retrieve_jd))
    registry.register(Tool("question_bank.search", "Search Qdrant-backed question bank.", search_question_bank))
    registry.register(Tool("knowledge.retrieve", "Retrieve domain knowledge.", retrieve_knowledge))
    registry.register(Tool("rubric.retrieve", "Retrieve scoring rubric.", retrieve_rubric))
    registry.register(Tool("answer.semantic_match", "Match answer against rubric/reference.", semantic_match))
    registry.register(Tool("evaluation.history", "Read evaluation history.", evaluation_history))
    registry.register(Tool("evidence.aggregate", "Aggregate evidence.", aggregate_evidence))
    return registry


