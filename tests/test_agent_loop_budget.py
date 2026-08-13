from __future__ import annotations

import asyncio

from interview_agent_runtime.blackboard import InterviewBlackboard
from interview_agent_runtime.memory import InMemorySessionMemory
from interview_agent_runtime.messages import AgentMessage
from interview_agent_runtime.providers import FakeLLMProvider
from interview_agent_runtime.runtime import AgentLoop, AgentRunRequest
from interview_agent_runtime.tools import Tool, ToolContext, ToolExecutor, ToolPolicy, ToolRegistry


def test_agent_loop_stops_when_max_rounds_is_exhausted():
    asyncio.run(_case())


async def _case():
    provider = FakeLLMProvider(
        responses=[
            {"tool_calls": [{"id": "call_1", "name": "ping", "arguments": {}}]},
            {"tool_calls": [{"id": "call_2", "name": "ping", "arguments": {}}]},
            {"tool_calls": [{"id": "call_3", "name": "ping", "arguments": {}}]},
        ]
    )
    registry = ToolRegistry()

    async def ping(context: ToolContext, args: dict[str, object]) -> dict[str, object]:
        return {"pong": True}

    registry.register(Tool("ping", "Ping", ping))
    executor = ToolExecutor(registry, ToolPolicy({"Agent": {"ping"}}))
    request = AgentRunRequest(
        session_id="budget",
        agent_name="Agent",
        skill_name="skill",
        initial_messages=[AgentMessage.user("loop")],
        visible_tools={"ping"},
        tool_executor=executor,
        tool_context=ToolContext("budget", "Agent", "skill", InterviewBlackboard("budget")),
        max_rounds=2,
        max_tool_calls=10,
    )

    result = await AgentLoop(provider, InMemorySessionMemory()).run(request)

    assert result.stop_reason == "max_rounds"
    assert result.rounds == 2
    assert result.tool_calls == 2
    assert len(provider.requests) == 2


def test_agent_loop_stops_when_tool_budget_is_exhausted():
    asyncio.run(_tool_budget_case())


async def _tool_budget_case():
    provider = FakeLLMProvider(
        responses=[
            {
                "tool_calls": [
                    {"id": "call_1", "name": "ping", "arguments": {}},
                    {"id": "call_2", "name": "ping", "arguments": {}},
                ]
            }
        ]
    )
    registry = ToolRegistry()

    async def ping(context: ToolContext, args: dict[str, object]) -> dict[str, object]:
        return {"pong": True}

    registry.register(Tool("ping", "Ping", ping))
    executor = ToolExecutor(registry, ToolPolicy({"Agent": {"ping"}}))
    request = AgentRunRequest(
        session_id="tool-budget",
        agent_name="Agent",
        skill_name="skill",
        initial_messages=[AgentMessage.user("loop")],
        visible_tools={"ping"},
        tool_executor=executor,
        tool_context=ToolContext(
            "tool-budget",
            "Agent",
            "skill",
            InterviewBlackboard("tool-budget"),
        ),
        max_rounds=4,
        max_tool_calls=1,
    )

    result = await AgentLoop(provider, InMemorySessionMemory()).run(request)

    assert result.stop_reason == "tool_budget_exceeded"
    assert result.tool_calls == 1
