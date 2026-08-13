from __future__ import annotations

import asyncio

from interview_agent_runtime.blackboard import InterviewBlackboard
from interview_agent_runtime.memory import InMemorySessionMemory
from interview_agent_runtime.messages import AgentMessage
from interview_agent_runtime.providers import FakeLLMProvider
from interview_agent_runtime.runtime import AgentLoop, AgentRunRequest
from interview_agent_runtime.tools import ToolContext, ToolExecutor, ToolPolicy, ToolRegistry


def test_agent_loop_can_exclude_interaction_and_domain_memory_for_minimal_projection():
    asyncio.run(_case())


async def _case():
    provider = FakeLLMProvider(responses=[{"content": '{"done": true}'}])
    memory = InMemorySessionMemory()
    registry = ToolRegistry()
    executor = ToolExecutor(registry, ToolPolicy({"ProfileAgent": set()}))
    board = InterviewBlackboard("projection")
    board.current_dimension = "Redis"
    board.capability_profile.verified_skills = ["Java"]

    result = await AgentLoop(provider, memory).run(
        AgentRunRequest(
            session_id="projection",
            agent_name="ProfileAgent",
            skill_name="profile-analysis",
            initial_messages=[AgentMessage.user("resume and jd")],
            visible_tools=set(),
            tool_executor=executor,
            tool_context=ToolContext(
                "projection",
                "ProfileAgent",
                "profile-analysis",
                board,
            ),
            blackboard=board,
            include_interaction_memory=False,
            include_domain_snapshot=False,
        )
    )

    assert result.stop_reason == "completed"
    assert [item.role.value for item in provider.requests[0].messages] == ["user"]
