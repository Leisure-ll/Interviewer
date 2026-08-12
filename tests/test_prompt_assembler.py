from __future__ import annotations

import json

from interview_agent_runtime.context import AgentContext
from interview_agent_runtime.domain import InterviewStage
from interview_agent_runtime.prompting import PromptAssembler
from interview_agent_runtime.skills import SkillDefinition


def test_prompt_assembler_combines_skill_context_and_schema():
    skill = SkillDefinition(name="evaluate-answer", prompt="Evaluate strictly.", output_schema="EvaluationArtifact")
    context = AgentContext(
        session_id="s",
        agent_name="EvaluatorAgent",
        skill_name="evaluate-answer",
        stage=InterviewStage.EVALUATING,
        authorized_tools={"rubric.retrieve"},
        token_budget=1000,
        timeout_seconds=10,
        retry=1,
    )
    messages = PromptAssembler().assemble(skill=skill, context=context, output_schema=skill.output_schema)

    assert messages[0]["content"] == "Evaluate strictly."
    payload = json.loads(messages[1]["content"])
    assert payload["context_type"] == "AgentContext"
    assert payload["output_schema"] == "EvaluationArtifact"
