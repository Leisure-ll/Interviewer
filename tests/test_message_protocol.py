from __future__ import annotations

import json

from interview_agent_runtime.messages import AgentMessage, MessageRole, ToolCall


def test_message_protocol_represents_all_roles_and_tool_call_linkage():
    call = ToolCall(id="call_1", name="resume.retrieve", arguments={"candidate_id": "c1"})
    messages = [
        AgentMessage.system("system"),
        AgentMessage.user("user"),
        AgentMessage.assistant(tool_calls=[call]),
        AgentMessage.tool("call_1", "resume.retrieve", '{"skills":["Java"]}'),
    ]

    assert [message.role for message in messages] == [
        MessageRole.SYSTEM,
        MessageRole.USER,
        MessageRole.ASSISTANT,
        MessageRole.TOOL,
    ]
    assert messages[2].tool_calls[0].name == "resume.retrieve"
    assert messages[3].tool_call_id == "call_1"
    assert json.loads(messages[2].to_dict()["tool_calls"][0]["function"]["arguments"]) == {
        "candidate_id": "c1"
    }
