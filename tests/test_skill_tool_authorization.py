from __future__ import annotations

from interview_agent_runtime.harness import InterviewHarness


def test_harness_loaded_skills_drive_tool_authorization():
    harness = InterviewHarness.from_config()
    runtime = harness.create_runtime()
    agent = runtime.agent_registry.resolve(next(iter(runtime.agent_registry.registered_stages())))
    skill = runtime.skill_registry.resolve(agent.required_skill(None))
    visible = runtime.tool_policy.authorize(agent.name, skill)

    assert visible <= set(skill.allowed_tools)
    assert visible <= runtime.tool_policy.agent_allowed_tools[agent.name]
