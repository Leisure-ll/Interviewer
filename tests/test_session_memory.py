from __future__ import annotations

import asyncio

from interview_agent_runtime.memory import InMemorySessionMemory
from interview_agent_runtime.messages import AgentMessage


def test_session_memory_isolated_and_supports_limit_and_clear():
    asyncio.run(_case())


async def _case():
    memory = InMemorySessionMemory()
    await memory.append("s1", AgentMessage.user("one"))
    await memory.append("s1", AgentMessage.assistant("two"))
    await memory.append("s2", AgentMessage.user("other"))

    assert [item.content for item in await memory.history("s1")] == ["one", "two"]
    assert [item.content for item in await memory.history("s1", limit=1)] == ["two"]
    assert [item.content for item in await memory.history("s2")] == ["other"]

    await memory.clear("s1")
    assert await memory.history("s1") == []
    assert [item.content for item in await memory.history("s2")] == ["other"]
