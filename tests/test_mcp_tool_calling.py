from __future__ import annotations

import asyncio

from interview_agent_runtime.blackboard import InterviewBlackboard
from interview_agent_runtime.memory import InMemorySessionMemory
from interview_agent_runtime.messages import AgentMessage
from interview_agent_runtime.providers import FakeLLMProvider
from interview_agent_runtime.runtime import AgentLoop, AgentRunRequest
from interview_agent_runtime.tools import (
    FakeMCPClient,
    MCPToolAdapter,
    MCPToolDefinition,
    ToolContext,
    ToolExecutor,
    ToolPolicy,
    ToolRegistry,
)


def test_agent_loop_executes_mcp_tool_through_unified_tool_runtime():
    asyncio.run(_case())


async def _case():
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
                        "id": "mcp-call",
                        "name": "mcp.knowledge.search",
                        "arguments": {"query": "cache"},
                    }
                ]
            },
            {"content": '{"done": true}'},
        ]
    )
    executor = ToolExecutor(
        registry,
        ToolPolicy({"QuestionAgent": {"mcp.knowledge.search"}}),
    )
    result = await AgentLoop(provider, InMemorySessionMemory()).run(
        AgentRunRequest(
            session_id="mcp-session",
            agent_name="QuestionAgent",
            skill_name="question-generation",
            initial_messages=[
                AgentMessage.system("system"),
                AgentMessage.user("search"),
            ],
            visible_tools={"mcp.knowledge.search"},
            tool_executor=executor,
            tool_context=ToolContext(
                "mcp-session",
                "QuestionAgent",
                "question-generation",
                InterviewBlackboard("mcp-session"),
            ),
        )
    )

    assert result.stop_reason == "completed"
    assert client.calls == [("knowledge.search", {"query": "cache"})]
    assert any(item.role.value == "tool" for item in result.messages)
