from __future__ import annotations

import asyncio

from interview_agent_runtime.blackboard import InterviewBlackboard
from interview_agent_runtime.tools import (
    FakeMCPClient,
    MCPToolAdapter,
    MCPToolDefinition,
    ToolContext,
    ToolExecutor,
    ToolPolicy,
    ToolRegistry,
)


def test_mcp_tools_are_registered_as_normal_tool_specs():
    asyncio.run(_case())


async def _case():
    client = FakeMCPClient(
        tools=[
            MCPToolDefinition(
                name="knowledge.search",
                description="Search knowledge",
                input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
            )
        ],
        responses={"knowledge.search": {"items": ["Cache Aside"]}},
    )
    registry = ToolRegistry()
    names = await MCPToolAdapter(client).load_tools(registry)

    assert names == ["mcp.knowledge.search"]
    assert registry.resolve(names[0]).spec.source == "mcp"
    result = await ToolExecutor(
        registry,
        ToolPolicy({"QuestionAgent": {"mcp.knowledge.search"}}),
    ).call(
        names[0],
        {"query": "cache"},
        ToolContext("s", "QuestionAgent", "question-generation", InterviewBlackboard("s")),
        {names[0]},
    )
    assert result == {"items": ["Cache Aside"]}
    assert client.calls == [("knowledge.search", {"query": "cache"})]
