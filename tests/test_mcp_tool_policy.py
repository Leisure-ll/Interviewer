from __future__ import annotations

import asyncio

from interview_agent_runtime.blackboard import InterviewBlackboard
from interview_agent_runtime.messages import ToolCall
from interview_agent_runtime.tools import (
    FakeMCPClient,
    MCPToolAdapter,
    MCPToolDefinition,
    ToolContext,
    ToolExecutor,
    ToolPolicy,
    ToolRegistry,
)
from interview_agent_runtime.skills import SkillDefinition


def test_mcp_tool_still_requires_agent_skill_and_session_policy():
    asyncio.run(_case())


async def _case():
    client = FakeMCPClient(
        tools=[MCPToolDefinition("knowledge.search", "Search knowledge")]
    )
    registry = ToolRegistry()
    await MCPToolAdapter(client).load_tools(registry)
    policy = ToolPolicy({"QuestionAgent": {"mcp.knowledge.search"}})
    skill = SkillDefinition(name="question-generation", allowed_tools=[])

    visible = policy.authorize(
        "QuestionAgent",
        skill,
        {"mcp.knowledge.search"},
    )
    result = await ToolExecutor(registry, policy).execute(
        ToolCall("call-mcp", "mcp.knowledge.search", {}),
        ToolContext("s", "QuestionAgent", skill.name, InterviewBlackboard("s")),
        visible,
    )

    assert visible == set()
    assert result.ok is False
    assert "not authorized" in (result.error or "")
