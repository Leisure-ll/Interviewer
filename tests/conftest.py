from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from interview_agent_runtime.harness import HarnessConfig, InterviewHarness
from interview_agent_runtime.runtime import InterviewRuntime, InterviewStateMachine
from interview_agent_runtime.runtime.execution_policy import TaskExecutor


def make_mock_runtime(**overrides) -> InterviewRuntime:
    harness = InterviewHarness.from_config(HarnessConfig.mock())
    values = {
        "state_machine": overrides.pop("state_machine", InterviewStateMachine()),
        "agent_registry": overrides.pop("agent_registry", harness.agent_registry),
        "skill_registry": overrides.pop("skill_registry", harness.skill_registry),
        "tool_registry": overrides.pop("tool_registry", harness.tool_registry),
        "tool_policy": overrides.pop("tool_policy", harness.tool_policy),
        "checkpoint_store": overrides.pop("checkpoint_store", harness.checkpoint_store),
        "event_bus": overrides.pop("event_bus", harness.event_bus),
        "executor": overrides.pop("executor", TaskExecutor()),
        "context_builder": overrides.pop("context_builder", harness.context_builder),
        "human_review_policy": overrides.pop("human_review_policy", None),
    }
    if overrides:
        raise TypeError(f"Unsupported runtime override(s): {', '.join(sorted(overrides))}")
    return InterviewRuntime(**values)
