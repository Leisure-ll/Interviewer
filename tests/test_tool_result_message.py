from __future__ import annotations

import asyncio
import json

from interview_agent_runtime.blackboard import InterviewBlackboard
from interview_agent_runtime.messages import ToolCall
from interview_agent_runtime.tools import Tool, ToolContext, ToolExecutor, ToolPolicy, ToolRegistry


def test_tool_executor_returns_correlated_tool_result():
    asyncio.run(_case())


async def _case():
    async def handler(context: ToolContext, args: dict[str, object]) -> dict[str, object]:
        return {"ok": True, "value": args["value"]}

    registry = ToolRegistry()
    registry.register(Tool("echo", "Echo value", handler))
    executor = ToolExecutor(registry, ToolPolicy({"Agent": {"echo"}}))
    context = ToolContext("s", "Agent", "skill", InterviewBlackboard("s"))

    result = await executor.execute(
        ToolCall(id="call_echo", name="echo", arguments={"value": "x"}),
        context,
        {"echo"},
    )

    assert result.ok is True
    assert result.tool_call_id == "call_echo"
    assert result.tool_name == "echo"
    assert json.loads(json.dumps(result.value)) == {"ok": True, "value": "x"}
