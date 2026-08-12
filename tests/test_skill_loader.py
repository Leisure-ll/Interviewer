from __future__ import annotations

from interview_agent_runtime.skills import SkillRegistry


def test_skill_loader_reads_frontmatter_and_prompt():
    registry = SkillRegistry.load_from_directory("skills")
    skill = registry.resolve("evaluate-answer")

    assert skill.agent == "EvaluatorAgent"
    assert "rubric.retrieve" in skill.allowed_tools
    assert skill.retry == 1
    assert "structured evidence" in skill.prompt
