from __future__ import annotations

import asyncio

from interview_agent_runtime.blackboard import InterviewBlackboard
from interview_agent_runtime.memory import InMemorySessionMemory
from interview_agent_runtime.messages import AgentMessage
from interview_agent_runtime.providers import FakeLLMProvider
from interview_agent_runtime.runtime import AgentLoop
from interview_agent_runtime.runtime.agent_loop import AgentRunRequest
from interview_agent_runtime.tools import Tool, ToolContext, ToolExecutor, ToolPolicy, ToolRegistry


def test_one_llm_iteration_can_request_many_tool_calls_without_confusing_round_budget():
    asyncio.run(_case())


async def _case():
    calls = []
    provider = FakeLLMProvider(
        responses=[
            {
                "tool_calls": [
                    {"id": "call_1", "name": "read", "arguments": {"path": "a"}},
                    {"id": "call_2", "name": "read", "arguments": {"path": "b"}},
                    {"id": "call_3", "name": "read", "arguments": {"path": "c"}},
                ]
            },
            {"content": '{"done": true}'},
        ]
    )
    registry = ToolRegistry()

    async def read(context, args):
        calls.append(args["path"])
        return {"path": args["path"]}

    registry.register(Tool("read", "Read resource", read))
    executor = ToolExecutor(registry, ToolPolicy({"Agent": {"read"}}))
    result = await AgentLoop(provider, InMemorySessionMemory()).run(
        AgentRunRequest(
            session_id="budget-vs-rounds",
            agent_name="Agent",
            skill_name="skill",
            initial_messages=[AgentMessage.user("read")],
            visible_tools={"read"},
            tool_executor=executor,
            tool_context=ToolContext("budget-vs-rounds", "Agent", "skill", InterviewBlackboard("budget-vs-rounds")),
            max_rounds=2,
            max_tool_calls=3,
        )
    )

    assert result.rounds == 2
    assert result.tool_calls == 3
    assert result.requested_tool_calls == 3
    assert result.executed_tool_calls == 3
    assert calls == ["a", "b", "c"]


def test_tool_call_batch_over_budget_is_rejected_as_a_batch():
    asyncio.run(_over_budget_case())


async def _over_budget_case():
    provider = FakeLLMProvider(
        responses=[
            {
                "tool_calls": [
                    {"id": "call_1", "name": "read", "arguments": {"path": "a"}},
                    {"id": "call_2", "name": "read", "arguments": {"path": "b"}},
                ]
            }
        ]
    )
    registry = ToolRegistry()
    executed = []

    async def read(context, args):
        executed.append(args["path"])
        return {"path": args["path"]}

    registry.register(Tool("read", "Read resource", read))
    result = await AgentLoop(provider, InMemorySessionMemory()).run(
        AgentRunRequest(
            session_id="batch-reject",
            agent_name="Agent",
            skill_name="skill",
            initial_messages=[AgentMessage.user("read")],
            visible_tools={"read"},
            tool_executor=ToolExecutor(registry, ToolPolicy({"Agent": {"read"}})),
            tool_context=ToolContext("batch-reject", "Agent", "skill", InterviewBlackboard("batch-reject")),
            max_rounds=3,
            max_tool_calls=1,
        )
    )

    assert result.stop_reason == "tool_budget_exceeded"
    assert result.executed_tool_calls == 0
    assert executed == []
    assert [message.role.value for message in result.messages[-2:]] == ["tool", "tool"]
