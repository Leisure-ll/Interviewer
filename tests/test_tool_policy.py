from __future__ import annotations

from conftest import make_mock_runtime
from interview_agent_runtime.runtime import InterviewStage


def test_tool_policy_uses_agent_skill_session_intersection():
    runtime = make_mock_runtime()
    agent = runtime.agent_registry.resolve(InterviewStage.NEXT_QUESTION)
    skill = runtime.skill_registry.resolve(agent.required_skill(None))
    visible = runtime.tool_policy.authorize(agent.name, skill, {"question_bank.search", "evaluation.history"})

    assert visible == {"question_bank.search"}
