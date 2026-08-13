from __future__ import annotations

import asyncio

from interview_agent_runtime.execution import ExecutionStrategy
from interview_agent_runtime.harness import HarnessConfig, InterviewHarness
from interview_agent_runtime.runtime import InterviewStage


def test_default_skills_declare_distinct_execution_strategies():
    harness = InterviewHarness.from_config(HarnessConfig.mock())
    skills = harness.skill_registry

    assert skills.resolve("profile-analysis").execution_strategy == ExecutionStrategy.REACT
    assert skills.resolve("question-generation").execution_strategy == ExecutionStrategy.DETERMINISTIC
    assert skills.resolve("evaluate-answer").execution_strategy == ExecutionStrategy.STRUCTURED_LLM


def test_runtime_resolves_strategy_and_emits_it_for_profile_run():
    asyncio.run(_case())


async def _case():
    harness = InterviewHarness.from_config(HarnessConfig.mock())
    runtime = harness.create_runtime("strategy")
    await runtime.start_session("strategy")
    await runtime.run_step("strategy")
    await runtime.run_step("strategy")

    started = next(
        event
        for event in runtime.event_bus.events
        if event.type.value == "AGENT_STARTED" and event.metadata.get("agent") == "ProfileAgent"
    )
    assert started.metadata["execution_strategy"] == ExecutionStrategy.REACT.value
    assert runtime.agent_registry.resolve(InterviewStage.PROFILE_ANALYSIS).execution_strategy == ExecutionStrategy.REACT
