from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from typing import Any

from interview_agent_runtime.context import AgentContext
from interview_agent_runtime.messages import AgentMessage
from interview_agent_runtime.skills import SkillDefinition


class PromptAssembler:
    def assemble(
        self,
        *,
        skill: SkillDefinition,
        context: AgentContext,
        output_schema: str,
    ) -> list[AgentMessage]:
        return [
            AgentMessage.system(skill.prompt or skill.description),
            AgentMessage.user(
                json.dumps(
                    {
                        "context_type": type(context).__name__,
                        "context": _to_json(context),
                        "output_schema": output_schema,
                        "instruction": "Return one valid JSON object only.",
                    },
                    ensure_ascii=False,
                )
            ),
        ]


def _to_json(value: Any) -> Any:
    if is_dataclass(value):
        return _to_json(asdict(value))
    if isinstance(value, dict):
        return {str(k): _to_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_json(item) for item in value]
    if hasattr(value, "value"):
        return value.value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value
