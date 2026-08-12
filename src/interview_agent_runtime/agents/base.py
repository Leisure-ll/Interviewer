from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from interview_agent_runtime.artifacts import AgentArtifact
from interview_agent_runtime.blackboard import InterviewBlackboard
from interview_agent_runtime.runtime.states import InterviewStage
from interview_agent_runtime.skills import SkillDefinition
from interview_agent_runtime.tools import ToolExecutor


@dataclass
class AgentDecision:
    should_run: bool
    confidence: float = 1.0
    reason: str = ""


class BaseInterviewAgent(ABC):
    name: str
    stages: set[InterviewStage]

    def decide(self, context: InterviewBlackboard) -> AgentDecision:
        return AgentDecision(context.current_stage in self.stages, reason=f"stage={context.current_stage.value}")

    @abstractmethod
    def required_skill(self, context: InterviewBlackboard) -> str:
        ...

    @abstractmethod
    async def execute(
        self,
        context: InterviewBlackboard,
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


