from __future__ import annotations

import asyncio

from interview_agent_runtime.blackboard import InterviewBlackboard
from interview_agent_runtime.execution import ExecutionStrategy
from interview_agent_runtime.memory import InMemorySessionMemory
from interview_agent_runtime.messages import AgentMessage
from interview_agent_runtime.providers import FakeLLMProvider
from interview_agent_runtime.runtime import AgentLoop
from interview_agent_runtime.runtime.agent_loop import AgentRunRequest
from interview_agent_runtime.tools import Tool, ToolContext, ToolExecutor, ToolPolicy, ToolRegistry


def test_agent_run_result_contains_execution_and_tool_governance_metrics():
    asyncio.run(_case())


async def _case():
    provider = FakeLLMProvider(
        responses=[
            {"tool_calls": [{"id": "1", "name": "read", "arguments": {"path": "a"}}]},
            {"tool_calls": [{"id": "2", "name": "read", "arguments": {"path": "a"}}]},
            {"content": '{"done": true}'},
        ]
    )
    registry = ToolRegistry()

    async def read(context, args):
        return {"content": "a"}

    registry.register(Tool("read", "Read", read))
    result = await AgentLoop(provider, InMemorySessionMemory()).run(
        AgentRunRequest(
            session_id="result",
            agent_name="Agent",
            skill_name="skill",
            initial_messages=[AgentMessage.user("read")],
            visible_tools={"read"},
            tool_executor=ToolExecutor(registry, ToolPolicy({"Agent": {"read"}})),
            tool_context=ToolContext("result", "Agent", "skill", InterviewBlackboard("result")),
            execution_strategy=ExecutionStrategy.REACT,
        )
    )

    assert result.stop_reason == "completed"
    assert result.execution_strategy == ExecutionStrategy.REACT
    assert result.rounds == 3
    assert result.tool_calls == 2
    assert result.unique_tool_calls == 1
    assert result.cache_hits == 1
    assert result.requested_tool_calls == 2
    assert result.executed_tool_calls == 2
    assert result.duration_ms >= 0
