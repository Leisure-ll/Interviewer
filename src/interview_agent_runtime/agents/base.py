from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from interview_agent_runtime.artifacts import AgentArtifact
from interview_agent_runtime.blackboard import InterviewBlackboard
from interview_agent_runtime.context import AgentContext
from interview_agent_runtime.domain import InterviewStage
from interview_agent_runtime.skills import SkillDefinition
from interview_agent_runtime.tools import ToolExecutor

if TYPE_CHECKING:
    from interview_agent_runtime.runtime.events import InMemoryEventBus


@dataclass
class AgentDecision:
    should_run: bool
    confidence: float = 1.0
    reason: str = ""


@dataclass
class AgentRunContext:
    session_id: str
    blackboard: InterviewBlackboard
    agent_context: AgentContext
    skill: SkillDefinition
    visible_tools: set[str]
    token_budget: int
    timeout_seconds: float
    retry: int
    tools: ToolExecutor
    agent_loop: object = None
    event_bus: Optional["InMemoryEventBus"] = None


class BaseInterviewAgent(ABC):
    name: str
    stages: set[InterviewStage]

    def decide(self, context: InterviewBlackboard) -> AgentDecision:
        return AgentDecision(context.current_stage in self.stages, reason=f"stage={context.current_stage.value}")

    async def execute_run(self, run_context: AgentRunContext) -> AgentArtifact:
        """Compatibility bridge while agents migrate to the unified run context."""
        return await self.execute(
            run_context.blackboard,
            run_context.agent_context,
            run_context.skill,
            run_context.tools,
            run_context.visible_tools,
        )

    @abstractmethod
    def required_skill(self, context: InterviewBlackboard) -> str:
        ...

    @abstractmethod
    async def execute(
        self,
        context: InterviewBlackboard,
        agent_context: AgentContext,
        skill: SkillDefinition,
        tools: ToolExecutor,
        visible_tools: set[str],
    ) -> AgentArtifact:
        ...


class InterviewAgentRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, BaseInterviewAgent] = {}
        self._stage_map: dict[InterviewStage, str] = {}

    def register(self, agent: BaseInterviewAgent) -> None:
        self._agents[agent.name] = agent
        for stage in agent.stages:
            self._stage_map[stage] = agent.name

    def resolve(self, stage: InterviewStage) -> BaseInterviewAgent:
        try:
            return self._agents[self._stage_map[stage]]
        except KeyError as exc:
            raise KeyError(f"No agent registered for stage: {stage.value}") from exc

    def agent_names(self) -> set[str]:
        return set(self._agents)

    def registered_stages(self) -> set[InterviewStage]:
        return set(self._stage_map)


