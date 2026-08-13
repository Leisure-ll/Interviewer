from __future__ import annotations

import asyncio

from interview_agent_runtime.harness import HarnessConfig, InterviewHarness
from interview_agent_runtime.harness.bootstrap import build_agent_registry
from interview_agent_runtime.providers import FakeLLMProvider
from interview_agent_runtime.runtime import InterviewStage


def test_profile_agent_uses_agent_loop_tool_calling_before_artifact_publish():
    asyncio.run(_case())


async def _case():
    provider = FakeLLMProvider(
        responses=[
            {"tool_calls": [{"id": "resume_call", "name": "resume.retrieve", "arguments": {}}]},
            {"tool_calls": [{"id": "jd_call", "name": "jd.retrieve", "arguments": {}}]},
            {
                "content": (
                    '{"candidate_profile":{"skills":["Java","Kafka"]},'
                    '"position_profile":{"role_name":"Platform Engineer"}}'
                )
            },
        ]
    )
    harness = InterviewHarness.from_config(HarnessConfig.mock())
    harness.llm_provider = provider
    harness.agent_registry = build_agent_registry(llm_provider=provider)
    runtime = harness.create_runtime("profile-loop")
    board = await runtime.start_session("profile-loop")

    await runtime.run_step(board.session_id)
    await runtime.run_step(board.session_id)
    board = await runtime.load_context(board.session_id)

    assert board.current_stage == InterviewStage.INTERVIEW_PLANNING
    assert board.candidate is not None
    assert board.candidate.skills == ["Java", "Kafka"]
    assert board.position_profile is not None
    assert board.position_profile.role_name == "Platform Engineer"
    assert [request.messages[-1].role.value for request in provider.requests] == [
        "user",
        "tool",
        "tool",
    ]
    assert any(event.type.value == "TOOL_SUCCEEDED" for event in runtime.event_bus.events)
