from __future__ import annotations

from interview_agent_runtime.tools import ToolSpec


def test_tool_spec_converts_to_provider_function_schema():
    spec = ToolSpec(
        name="resume.retrieve",
        description="Retrieve resume",
        input_schema={
            "type": "object",
            "properties": {"candidate_id": {"type": "string"}},
            "required": ["candidate_id"],
        },
    )

    assert spec.to_provider_schema() == {
        "type": "function",
        "function": {
            "name": "resume.retrieve",
            "description": "Retrieve resume",
            "parameters": {
                "type": "object",
                "properties": {"candidate_id": {"type": "string"}},
                "required": ["candidate_id"],
            },
        },
    }
