from __future__ import annotations

from interview_agent_runtime.harness import HarnessConfig, InterviewHarness
from interview_agent_runtime.runtime import InterviewRuntime


def test_harness_creates_runtime_with_injected_registries_and_policies():
    harness = InterviewHarness.from_config(HarnessConfig.mock())
    runtime = harness.create_runtime("boundary")

    assert isinstance(runtime, InterviewRuntime)
    assert runtime.agent_registry is harness.agent_registry
    assert runtime.skill_registry is harness.skill_registry
    assert runtime.tool_policy is harness.tool_policy
    assert runtime.checkpoint_store is harness.checkpoint_store


def test_harness_does_not_control_runtime_state_machine():
    harness = InterviewHarness.from_config(HarnessConfig.mock())

    assert not hasattr(harness, "transition")
    assert not hasattr(harness, "run_step")
    assert not hasattr(harness, "receive_answer")
