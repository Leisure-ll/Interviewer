from __future__ import annotations

import asyncio

from interview_agent_runtime.blackboard import InterviewBlackboard
from interview_agent_runtime.memory import InMemorySessionMemory
from interview_agent_runtime.messages import AgentMessage, ToolCall
from interview_agent_runtime.tools import (
    Tool,
    ToolContext,
    ToolExecutor,
    ToolGovernanceState,
    ToolInvocationKey,
    ToolPolicy,
    ToolRegistry,
    ToolSpec,
)


def test_tool_invocation_key_canonicalizes_argument_order():
    left = ToolInvocationKey.from_call("read", {"path": "a", "encoding": "utf-8"})
    right = ToolInvocationKey.from_call("read", {"encoding": "utf-8", "path": "a"})
    assert left == right
    assert left.fingerprint == right.fingerprint


def test_read_tool_cache_and_duplicate_guard_are_distinct():
    asyncio.run(_case())


async def _case():
    count = 0
    registry = ToolRegistry()

    async def read(context, args):
        nonlocal count
        count += 1
        return {"content": "v1"}

    registry.register(Tool("read", "Read", read))
    executor = ToolExecutor(registry, ToolPolicy({"Agent": {"read"}}))
    context = ToolContext("governance", "Agent", "skill", InterviewBlackboard("governance"))
    governance = ToolGovernanceState(max_duplicate_calls=1)
    visible = {"read"}

    first = await executor.execute(ToolCall("1", "read", {"path": "a"}), context, visible, governance=governance)
    second = await executor.execute(ToolCall("2", "read", {"path": "a"}), context, visible, governance=governance)
    third = await executor.execute(ToolCall("3", "read", {"path": "a"}), context, visible, governance=governance)

    assert first.ok
    assert second.ok and second.cache_hit
    assert not third.ok and third.duplicate
    assert count == 1
    assert governance.cache_hits == 1
    assert governance.duplicate_calls == 1


def test_resource_version_changes_cache_identity():
    asyncio.run(_version_case())


class VersionResolver:
    def __init__(self):
        self.version = "v1"

    async def version_for(self, tool, arguments):
        return self.version


async def _version_case():
    count = 0
    resolver = VersionResolver()
    registry = ToolRegistry()

    async def read(context, args):
        nonlocal count
        count += 1
        return {"version": resolver.version}

    registry.register(Tool("read", "Read", read))
    executor = ToolExecutor(registry, ToolPolicy({"Agent": {"read"}}), resolver)
    context = ToolContext("version", "Agent", "skill", InterviewBlackboard("version"))
    governance = ToolGovernanceState()

    await executor.execute(ToolCall("1", "read", {"path": "a"}), context, {"read"}, governance=governance)
    await executor.execute(ToolCall("2", "read", {"path": "a"}), context, {"read"}, governance=governance)
    resolver.version = "v2"
    await executor.execute(ToolCall("3", "read", {"path": "a"}), context, {"read"}, governance=governance)

    assert count == 2


def test_side_effect_duplicate_is_not_cached_as_success():
    asyncio.run(_side_effect_case())


async def _side_effect_case():
    count = 0
    registry = ToolRegistry()

    async def send(context, args):
        nonlocal count
        count += 1
        return {"sent": True}

    registry.register(
        Tool(
            spec=ToolSpec(
                name="notification.send",
                description="Send notification",
                side_effect=True,
                idempotent=False,
            ),
            handler=send,
        )
    )
    executor = ToolExecutor(registry, ToolPolicy({"Agent": {"notification.send"}}))
    context = ToolContext("side-effect", "Agent", "skill", InterviewBlackboard("side-effect"))
    governance = ToolGovernanceState()

    first = await executor.execute(
        ToolCall("1", "notification.send", {"candidate_id": "123"}),
        context,
        {"notification.send"},
        governance=governance,
    )
    second = await executor.execute(
        ToolCall("2", "notification.send", {"candidate_id": "123"}),
        context,
        {"notification.send"},
        governance=governance,
    )

    assert first.ok
    assert not second.ok and second.duplicate
    assert count == 1


def test_retryable_failure_is_not_treated_as_successful_duplicate():
    asyncio.run(_retry_case())


async def _retry_case():
    count = 0
    registry = ToolRegistry()

    async def flaky(context, args):
        nonlocal count
        count += 1
        if count == 1:
            raise TimeoutError("temporary")
        return {"ok": True}

    registry.register(Tool("search", "Search", flaky))
    executor = ToolExecutor(registry, ToolPolicy({"Agent": {"search"}}))
    context = ToolContext("retry", "Agent", "skill", InterviewBlackboard("retry"))
    governance = ToolGovernanceState()

    first = await executor.execute(ToolCall("1", "search", {}), context, {"search"}, governance=governance)
    second = await executor.execute(ToolCall("2", "search", {}), context, {"search"}, governance=governance)

    assert not first.ok
    assert second.ok
    assert count == 2
