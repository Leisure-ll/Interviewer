from __future__ import annotations

from pathlib import Path

from interview_agent_runtime.agents import (
    EvaluatorAgent,
    FollowUpAgent,
    InterviewAgentRegistry,
    PlannerAgent,
    ProfileAgent,
    QuestionAgent,
    ReportAgent,
)
from interview_agent_runtime.checkpoint import CheckpointStore, InMemoryCheckpointStore, JsonFileCheckpointStore
from interview_agent_runtime.context import AgentContextBuilder, ContextBudget
from interview_agent_runtime.harness.config import HarnessConfig
from interview_agent_runtime.harness.harness import InterviewHarness
from interview_agent_runtime.memory import InMemorySessionMemory, RecentWindowMemoryCompressor
from interview_agent_runtime.observability import (
    CompositeObserver,
    InMemoryTraceStore,
    NoopObserver,
    TraceObserver,
)
from interview_agent_runtime.providers import FakeLLMProvider, OpenAICompatibleLLMProvider
from interview_agent_runtime.runtime.events import InMemoryEventBus
from interview_agent_runtime.skills import SkillRegistry
from interview_agent_runtime.tools import ToolPolicy, ToolRegistry
from interview_agent_runtime.tools.default_tools import build_default_tool_registry


def build_harness(config: HarnessConfig) -> InterviewHarness:
    if config.mode == "mock":
        return build_mock_harness(config)
    if config.mode == "development":
        return build_development_harness(config)
    if config.mode == "production":
        return build_production_harness(config)
    raise ValueError(f"Unsupported harness mode: {config.mode}")


def build_mock_harness(config: HarnessConfig) -> InterviewHarness:
    return _assemble(
        config=config,
        tool_registry=build_default_tool_registry(),
        checkpoint_store=InMemoryCheckpointStore(),
        llm_provider=FakeLLMProvider(
            responses=[
                {"tool_calls": [{"id": "mock_resume", "name": "resume.retrieve", "arguments": {}}]},
                {"tool_calls": [{"id": "mock_jd", "name": "jd.retrieve", "arguments": {}}]},
                {},
            ]
        ),
    )


def build_development_harness(config: HarnessConfig) -> InterviewHarness:
    checkpoint_store: CheckpointStore
    if config.checkpoint_dir is None:
        checkpoint_store = InMemoryCheckpointStore()
    else:
        checkpoint_store = JsonFileCheckpointStore(config.checkpoint_dir)
    return _assemble(
        config=config,
        tool_registry=build_default_tool_registry(),
        checkpoint_store=checkpoint_store,
        llm_provider=OpenAICompatibleLLMProvider(
            api_key=config.llm_api_key,
            base_url=config.llm_base_url,
            model=config.llm_model,
        )
        if config.llm_api_key
        else FakeLLMProvider(),
    )


def build_production_harness(config: HarnessConfig) -> InterviewHarness:
    if config.checkpoint_dir is None:
        raise ValueError("production harness requires checkpoint_dir")
    return _assemble(
        config=config,
        tool_registry=build_default_tool_registry(),
        checkpoint_store=JsonFileCheckpointStore(config.checkpoint_dir),
        llm_provider=OpenAICompatibleLLMProvider(
            api_key=config.llm_api_key,
            base_url=config.llm_base_url,
            model=config.llm_model,
        ),
    )


def _assemble(
    *,
    config: HarnessConfig,
    tool_registry: ToolRegistry,
    checkpoint_store: CheckpointStore,
    llm_provider,
) -> InterviewHarness:
    skills_dir = config.skills_dir or _default_skills_dir()
    observer = NoopObserver()
    trace_store = InMemoryTraceStore()
    event_observer = CompositeObserver(
        [observer, TraceObserver(trace_store)]
    )
    return InterviewHarness(
        config=config,
        agent_registry=build_agent_registry(llm_provider=llm_provider),
        skill_registry=SkillRegistry.load_from_directory(skills_dir),
        tool_registry=tool_registry,
        tool_policy=ToolPolicy(),
        checkpoint_store=checkpoint_store,
        context_builder=AgentContextBuilder(ContextBudget()),
        event_bus=InMemoryEventBus(observer=event_observer),
        observer=observer,
        trace_store=trace_store,
        llm_provider=llm_provider,
        memory=InMemorySessionMemory(),
        memory_compressor=RecentWindowMemoryCompressor(),
    )


def build_agent_registry(llm_provider=None) -> InterviewAgentRegistry:
    registry = InterviewAgentRegistry()
    for agent in [
        ProfileAgent(llm_provider=llm_provider),
        PlannerAgent(),
        QuestionAgent(),
        EvaluatorAgent(llm_provider=llm_provider),
        FollowUpAgent(llm_provider=llm_provider),
        ReportAgent(),
    ]:
        registry.register(agent)
    return registry


def _default_skills_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "skills"
