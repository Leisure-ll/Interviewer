from __future__ import annotations

import asyncio

from interview_agent_runtime.blackboard import InterviewBlackboard
from interview_agent_runtime.memory import InMemorySessionMemory
from interview_agent_runtime.messages import AgentMessage
from interview_agent_runtime.providers import FakeLLMProvider
from interview_agent_runtime.runtime import AgentLoop
from interview_agent_runtime.runtime.agent_loop import AgentRunRequest
from interview_agent_runtime.tools import Tool, ToolContext, ToolExecutor, ToolPolicy, ToolRegistry


def test_bulk_tool_can_replace_many_mechanical_calls_in_one_invocation():
    asyncio.run(_case())


async def _case():
    provider = FakeLLMProvider(
        responses=[
            {
                "tool_calls": [
                    {
                        "id": "bulk_1",
                        "name": "read_files",
                        "arguments": {"paths": ["a.py", "b.py", "c.py"]},
                    }
                ]
            },
            {"content": '{"done": true}'},
        ]
    )
    registry = ToolRegistry()
    seen = []

    async def read_files(context, args):
        seen.extend(args["paths"])
        return {"files": {path: "content" for path in args["paths"]}}

    registry.register(Tool("read_files", "Read many files in one call", read_files))
    result = await AgentLoop(provider, InMemorySessionMemory()).run(
        AgentRunRequest(
            session_id="bulk",
            agent_name="Agent",
            skill_name="skill",
            initial_messages=[AgentMessage.user("read files")],
            visible_tools={"read_files"},
            tool_executor=ToolExecutor(registry, ToolPolicy({"Agent": {"read_files"}})),
            tool_context=ToolContext("bulk", "Agent", "skill", InterviewBlackboard("bulk")),
            max_rounds=2,
            max_tool_calls=2,
        )
    )

    assert result.stop_reason == "completed"
    assert result.rounds == 2
    assert result.tool_calls == 1
    assert seen == ["a.py", "b.py", "c.py"]
