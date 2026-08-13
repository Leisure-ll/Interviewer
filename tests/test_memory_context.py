from __future__ import annotations

import asyncio

from interview_agent_runtime.blackboard import InterviewBlackboard
from interview_agent_runtime.memory import (
    InMemorySessionMemory,
    MemoryContextBuilder,
    MemoryScope,
)
from interview_agent_runtime.messages import AgentMessage


def test_memory_context_combines_old_summary_recent_messages_domain_snapshot_and_current_scope():
    asyncio.run(_case())


async def _case():
    memory = InMemorySessionMemory()
    scope = MemoryScope("memory-context", "EvaluatorAgent")
    for index in range(4):
        await memory.append(scope, AgentMessage.user("old-{0}".format(index)))
    await memory.append(scope, AgentMessage.assistant("recent"))
    board = InterviewBlackboard("memory-context")
    board.current_dimension = "Redis"
    board.capability_profile.verified_skills = ["Java"]

    context = await MemoryContextBuilder(memory).build(
        scope,
        blackboard=board,
        max_recent_messages=2,
    )

    assert context.summary is not None
    assert [item.content for item in context.recent_messages] == ["old-3", "recent"]
    assert context.domain_snapshot is not None
    assert context.domain_snapshot.current_dimension == "Redis"
    assert context.to_messages()[-2].content == "old-3"
