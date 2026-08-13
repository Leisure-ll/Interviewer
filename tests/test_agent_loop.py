from __future__ import annotations

import asyncio

from interview_agent_runtime.blackboard import InterviewBlackboard
from interview_agent_runtime.memory import InMemorySessionMemory
from interview_agent_runtime.messages import AgentMessage
from interview_agent_runtime.providers import FakeLLMProvider
from interview_agent_runtime.runtime import AgentLoop, AgentRunRequest
from interview_agent_runtime.tools import Tool, ToolContext, ToolExecutor, ToolPolicy, ToolRegistry


def test_agent_loop_runs_assistant_tool_result_assistant_round_trip():
    asyncio.run(_case())


async def _case():
    provider = FakeLLMProvider(
        responses=[
            {"tool_calls": [{"id": "call_1", "name": "resume.retrieve", "arguments": {}}]},
            {"content": '{"done": true}'},
        ]
    )
    memory = InMemorySessionMemory()
    registry = ToolRegistry()

    async def retrieve(context: ToolContext, args: dict[str, object]) -> dict[str, object]:
        return {"skills": ["Java"]}

    registry.register(Tool("resume.retrieve", "Retrieve resume", retrieve))
    executor = ToolExecutor(registry, ToolPolicy({"ProfileAgent": {"resume.retrieve"}}))
    board = InterviewBlackboard("loop")
    request = AgentRunRequest(
        session_id="loop",
        agent_name="ProfileAgent",
        skill_name="profile-analysis",
        initial_messages=[AgentMessage.system("system"), AgentMessage.user("inspect")],
        visible_tools={"resume.retrieve"},
        tool_executor=executor,
        tool_context=ToolContext("loop", "ProfileAgent", "profile-analysis", board),
        response_schema="ProfileDraft",
        memory_key="loop:ProfileAgent",
    )

    result = await AgentLoop(provider, memory).run(request)
    history = await memory.history("loop:ProfileAgent")

    assert result.stop_reason == "completed"
    assert result.rounds == 2
    assert result.tool_calls == 1
    assert result.parsed == {"done": True}
    assert [item.role.value for item in history] == [
        "system",
        "user",
        "assistant",
        "tool",
        "assistant",
    ]
    assert history[3].tool_call_id == "call_1"
    assert provider.requests[1].messages[-1].role.value == "tool"
