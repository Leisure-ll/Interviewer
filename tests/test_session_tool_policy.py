from __future__ import annotations

from interview_agent_runtime.skills import SkillDefinition
from interview_agent_runtime.tools import ToolPolicy


def test_session_tool_policy_is_three_way_intersection():
    policy = ToolPolicy(
        agent_allowed_tools={"Agent": {"A", "B", "C"}}
    )
    skill = SkillDefinition(
        name="skill",
        allowed_tools=["B", "C", "D"],
    )

    assert policy.authorize("Agent", skill, {"C", "D", "E"}) == {"C"}
