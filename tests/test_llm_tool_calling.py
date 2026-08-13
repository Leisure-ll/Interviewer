from __future__ import annotations

import json

from interview_agent_runtime.messages import MessageRole
from interview_agent_runtime.providers.llm import _message_from_provider


def test_openai_compatible_response_is_converted_to_typed_tool_call_message():
    message = _message_from_provider(
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_resume",
                    "type": "function",
                    "function": {
                        "name": "resume.retrieve",
                        "arguments": json.dumps({"candidate_id": "c1"}),
                    },
                }
            ],
        }
    )

    assert message.role == MessageRole.ASSISTANT
    assert message.content is None
    assert len(message.tool_calls) == 1
    assert message.tool_calls[0].id == "call_resume"
    assert message.tool_calls[0].name == "resume.retrieve"
    assert message.tool_calls[0].arguments == {"candidate_id": "c1"}
