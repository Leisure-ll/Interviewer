from __future__ import annotations

import asyncio

from interview_agent_runtime.memory import InMemorySessionMemory, MemoryScope
from interview_agent_runtime.messages import AgentMessage


def test_memory_scope_isolates_agents_and_accepts_typed_scope():
    asyncio.run(_case())


async def _case():
    memory = InMemorySessionMemory()
    profile = MemoryScope("session-1", "ProfileAgent")
    evaluator = MemoryScope("session-1", "EvaluatorAgent")

    await memory.append(profile, AgentMessage.user("resume"))
    await memory.append(evaluator, AgentMessage.user("answer"))

    assert [item.content for item in await memory.history(profile)] == ["resume"]
    assert [item.content for item in await memory.history(evaluator)] == ["answer"]
    assert profile.key() != evaluator.key()
