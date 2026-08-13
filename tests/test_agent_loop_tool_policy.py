from __future__ import annotations

import asyncio
import json

from interview_agent_runtime.blackboard import InterviewBlackboard
from interview_agent_runtime.memory import InMemorySessionMemory
from interview_agent_runtime.messages import AgentMessage
from interview_agent_runtime.providers import FakeLLMProvider
from interview_agent_runtime.runtime import AgentLoop, AgentRunRequest
from interview_agent_runtime.tools import Tool, ToolContext, ToolExecutor, ToolPolicy, ToolRegistry


def test_agent_loop_rejects_unauthorized_tool_call_without_executing_handler():
    asyncio.run(_case())


async def _case():
    calls = []

    async def forbidden_handler(context: ToolContext, args: dict[str, object]) -> dict[str, object]:
        calls.append(args)
        return {"should_not": "run"}

    provider = FakeLLMProvider(
        responses=[
            {
                "tool_calls": [
                    {
                        "id": "forbidden_call",
                        "name": "private.lookup",
                        "arguments": {"key": "secret"},
                    }
                ]
            },
            {"content": '{"done": true}'},
        ]
    )
    registry = ToolRegistry()
    registry.register(Tool("private.lookup", "Private lookup", forbidden_handler))
    executor = ToolExecutor(
        registry,
        ToolPolicy({"ProfileAgent": {"resume.retrieve"}}),
    )
    memory = InMemorySessionMemory()
    request = AgentRunRequest(
        session_id="policy-loop",
        agent_name="ProfileAgent",
        skill_name="profile-analysis",
        initial_messages=[AgentMessage.system("system"), AgentMessage.user("inspect")],
        visible_tools=set(),
        tool_executor=executor,
        tool_context=ToolContext(
            "policy-loop",
            "ProfileAgent",
            "profile-analysis",
            InterviewBlackboard("policy-loop"),
        ),
        response_schema="ProfileDraft",
        memory_key="policy-loop:ProfileAgent",
    )

    result = await AgentLoop(provider, memory).run(request)
    history = await memory.history("policy-loop:ProfileAgent")

    assert result.stop_reason == "completed"
    assert calls == []
    assert history[3].role.value == "tool"
    assert history[3].tool_call_id == "forbidden_call"
    assert json.loads(history[3].content or "{}")["ok"] is False
    assert "not authorized" in json.loads(history[3].content or "{}")["error"]
