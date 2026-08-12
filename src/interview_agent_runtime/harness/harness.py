from __future__ import annotations

from pathlib import Path
from typing import Optional

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
from interview_agent_runtime.runtime import InterviewRuntime
from interview_agent_runtime.runtime.events import InMemoryEventBus
from interview_agent_runtime.runtime.execution_policy import TaskExecutor
from interview_agent_runtime.runtime.state_machine import InterviewStateMachine
from interview_agent_runtime.skills import SkillRegistry
from interview_agent_runtime.tools import ToolPolicy
from interview_agent_runtime.tools.default_tools import build_default_tool_registry


class InterviewHarness:
    def __init__(
        self,
        *,
        config: HarnessConfig,
        agent_registry: InterviewAgentRegistry,
        skill_registry: SkillRegistry,
        tool_policy: ToolPolicy,
        checkpoint_store: CheckpointStore,
        context_builder: AgentContextBuilder,
        event_bus: InMemoryEventBus,
    ) -> None:
        self.config = config
        self.agent_registry = agent_registry
        self.skill_registry = skill_registry
        self.tool_registry = build_default_tool_registry()
        self.tool_policy = tool_policy
        self.checkpoint_store = checkpoint_store
        self.context_builder = context_builder
        self.event_bus = event_bus

    @classmethod
    def from_config(cls, config: Optional[HarnessConfig] = None) -> "InterviewHarness":
        resolved = config or HarnessConfig.mock()
        skills_dir = resolved.skills_dir or _default_skills_dir()
        skill_registry = SkillRegistry.load_from_directory(skills_dir)
        checkpoint_store: CheckpointStore
        if resolved.mode == "mock" or resolved.checkpoint_dir is None:
            checkpoint_store = InMemoryCheckpointStore()
        else:
            checkpoint_store = JsonFileCheckpointStore(resolved.checkpoint_dir)
        return cls(
            config=resolved,
            agent_registry=_build_agent_registry(),
            skill_registry=skill_registry,
            tool_policy=ToolPolicy(),
            checkpoint_store=checkpoint_store,
            context_builder=AgentContextBuilder(ContextBudget()),
            event_bus=InMemoryEventBus(),
        )

    def create_runtime(self, session_id: Optional[str] = None) -> InterviewRuntime:
        _ = session_id
        return InterviewRuntime(
            state_machine=InterviewStateMachine(),
            agent_registry=self.agent_registry,
            skill_registry=self.skill_registry,
            tool_registry=self.tool_registry,
            tool_policy=self.tool_policy,
            checkpoint_store=self.checkpoint_store,
            event_bus=self.event_bus,
            executor=TaskExecutor(),
            context_builder=self.context_builder,
        )


def _build_agent_registry() -> InterviewAgentRegistry:
    registry = InterviewAgentRegistry()
    for agent in [ProfileAgent(), PlannerAgent(), QuestionAgent(), EvaluatorAgent(), FollowUpAgent(), ReportAgent()]:
        registry.register(agent)
    return registry


def _default_skills_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "skills"
