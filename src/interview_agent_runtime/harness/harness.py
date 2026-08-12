from __future__ import annotations

from typing import Optional

from interview_agent_runtime.agents import InterviewAgentRegistry
from interview_agent_runtime.checkpoint import CheckpointStore
from interview_agent_runtime.context import AgentContextBuilder
from interview_agent_runtime.harness.config import HarnessConfig
from interview_agent_runtime.observability import Observer
from interview_agent_runtime.providers import LLMProvider
from interview_agent_runtime.runtime import InterviewRuntime
from interview_agent_runtime.runtime.events import InMemoryEventBus
from interview_agent_runtime.runtime.execution_policy import TaskExecutor
from interview_agent_runtime.runtime.state_machine import InterviewStateMachine
from interview_agent_runtime.skills import SkillRegistry
from interview_agent_runtime.tools import ToolPolicy, ToolRegistry


class InterviewHarness:
    def __init__(
        self,
        *,
        config: HarnessConfig,
        agent_registry: InterviewAgentRegistry,
        skill_registry: SkillRegistry,
        tool_registry: ToolRegistry,
        tool_policy: ToolPolicy,
        checkpoint_store: CheckpointStore,
        context_builder: AgentContextBuilder,
        event_bus: InMemoryEventBus,
        observer: Observer,
        llm_provider: Optional[LLMProvider] = None,
    ) -> None:
        self.config = config
        self.agent_registry = agent_registry
        self.skill_registry = skill_registry
        self.tool_registry = tool_registry
        self.tool_policy = tool_policy
        self.checkpoint_store = checkpoint_store
        self.context_builder = context_builder
        self.event_bus = event_bus
        self.observer = observer
        self.llm_provider = llm_provider

    @classmethod
    def from_config(cls, config: Optional[HarnessConfig] = None) -> "InterviewHarness":
        from interview_agent_runtime.harness.bootstrap import build_harness

        return build_harness(config or HarnessConfig.mock())

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
