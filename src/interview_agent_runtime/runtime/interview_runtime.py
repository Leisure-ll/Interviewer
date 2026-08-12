from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from uuid import uuid4

from interview_agent_runtime.agents import (
    EvaluatorAgent,
    FollowUpAgent,
    InterviewAgentRegistry,
    PlannerAgent,
    ProfileAgent,
    QuestionAgent,
    ReportAgent,
)
from interview_agent_runtime.artifacts import AgentArtifact, AnswerArtifact
from interview_agent_runtime.blackboard import InterviewBlackboard
from interview_agent_runtime.checkpoint import CheckpointStore, InMemoryCheckpointStore
from interview_agent_runtime.runtime.events import InMemoryEventBus, RuntimeEvent, RuntimeEventType
from interview_agent_runtime.runtime.execution_policy import ExecutionPolicy, TaskExecutor
from interview_agent_runtime.runtime.state_machine import InterviewStateMachine
from interview_agent_runtime.runtime.states import InterviewStage
from interview_agent_runtime.skills import SkillRegistry
from interview_agent_runtime.tools import ToolExecutor, ToolPolicy, ToolRegistry
from interview_agent_runtime.tools.default_tools import build_default_tool_registry


@dataclass
class RuntimeStepResult:
    session_id: str
    previous_stage: InterviewStage
    current_stage: InterviewStage
    artifact: Optional[AgentArtifact]


class InterviewRuntime:
    def __init__(
        self,
        *,
        state_machine: Optional[InterviewStateMachine] = None,
        agent_registry: Optional[InterviewAgentRegistry] = None,
        skill_registry: Optional[SkillRegistry] = None,
        tool_registry: Optional[ToolRegistry] = None,
        tool_policy: Optional[ToolPolicy] = None,
        checkpoint_store: Optional[CheckpointStore] = None,
        event_bus: Optional[InMemoryEventBus] = None,
        executor: Optional[TaskExecutor] = None,
    ) -> None:
        self.state_machine = state_machine or InterviewStateMachine()
        self.agent_registry = agent_registry or self._default_agents()
        self.skill_registry = skill_registry or SkillRegistry.with_defaults()
        self.tool_registry = tool_registry or build_default_tool_registry()
        self.tool_policy = tool_policy or ToolPolicy()
        self.tool_executor = ToolExecutor(self.tool_registry, self.tool_policy)
        self.checkpoint_store = checkpoint_store or InMemoryCheckpointStore()
        self.event_bus = event_bus or InMemoryEventBus()
        self.executor = executor or TaskExecutor()

    async def start_session(self, session_id: Optional[str] = None) -> InterviewBlackboard:
        board = InterviewBlackboard(session_id=session_id or f"session_{uuid4().hex[:12]}")
        await self.checkpoint_store.save(board)
        await self.event_bus.emit(RuntimeEvent(RuntimeEventType.SESSION_STARTED, board.session_id))
        return board

    async def load_context(self, session_id: str) -> InterviewBlackboard:
        context = await self.checkpoint_store.load(session_id)
        if context is None:
            raise KeyError(f"Session not found: {session_id}")
        return context

    async def receive_answer(self, session_id: str, text: str) -> RuntimeStepResult:
        context = await self.load_context(session_id)
        if context.current_stage != InterviewStage.LISTENING:
            raise RuntimeError(f"Session is not listening: {context.current_stage.value}")
        if context.current_question is None:
            raise RuntimeError("No current question")
        artifact = AnswerArtifact(owner="Candidate", question_id=context.current_question.question_id, text=text)
        context.publish(artifact)
        previous = context.current_stage
        context.current_stage = self.state_machine.transition(previous, context, artifact)
        await self.checkpoint_store.save(context)
        await self.event_bus.emit(RuntimeEvent(RuntimeEventType.ANSWER_RECEIVED, session_id, metadata={"answer_id": artifact.answer_id}))
        await self.event_bus.emit(
            RuntimeEvent(
                RuntimeEventType.STATE_TRANSITIONED,
                session_id,
                metadata={"from": previous.value, "to": context.current_stage.value},
            )
        )
        return RuntimeStepResult(session_id, previous, context.current_stage, artifact)

    async def run_step(self, session_id: str) -> RuntimeStepResult:
        context = await self.load_context(session_id)
        previous = context.current_stage
        artifact: Optional[AgentArtifact] = None

        if previous in {InterviewStage.QUESTIONING}:
            context.current_stage = self.state_machine.transition(previous, context, None)
            await self.checkpoint_store.save(context)
            await self.event_bus.emit(RuntimeEvent(RuntimeEventType.QUESTION_ASKED, session_id))
            return RuntimeStepResult(session_id, previous, context.current_stage, None)

        if previous in {InterviewStage.FINISHED, InterviewStage.FAILED}:
            return RuntimeStepResult(session_id, previous, previous, None)

        if previous == InterviewStage.INIT:
            context.current_stage = self.state_machine.transition(previous, context, None)
            await self.checkpoint_store.save(context)
            return RuntimeStepResult(session_id, previous, context.current_stage, None)

        agent = self.agent_registry.resolve(previous)
        decision = agent.decide(context)
        if not decision.should_run:
            raise RuntimeError(f"Agent refused stage {previous.value}: {decision.reason}")

        skill = self.skill_registry.resolve(agent.required_skill(context))
        visible_tools = self.tool_policy.authorize(agent.name, skill)
        policy = ExecutionPolicy(timeout_seconds=skill.timeout, retry=skill.retry, name=f"{agent.name}:{skill.name}")

        result = await self.executor.execute(
            lambda: agent.execute(context, skill, self.tool_executor, visible_tools),
            policy,
        )
        if not result.ok or result.value is None:
            context.runtime_metadata.errors.append(str(result.error))
            context.current_stage = InterviewStage.FAILED
            await self.checkpoint_store.save(context)
            await self.event_bus.emit(RuntimeEvent(RuntimeEventType.RUNTIME_ERROR, session_id, message=str(result.error)))
            return RuntimeStepResult(session_id, previous, context.current_stage, None)

        artifact = result.value
        context.publish(artifact)
        context.current_stage = self.state_machine.transition(previous, context, artifact)

        await self.checkpoint_store.save(context)
        await self._emit_artifact_event(context, artifact, previous)
        await self.event_bus.emit(
            RuntimeEvent(
                RuntimeEventType.STATE_TRANSITIONED,
                session_id,
                metadata={"from": previous.value, "to": context.current_stage.value, "artifact": artifact.kind},
            )
        )
        return RuntimeStepResult(session_id, previous, context.current_stage, artifact)

    async def run_until_waiting_or_done(self, session_id: str, max_steps: int = 20) -> InterviewBlackboard:
        for _ in range(max_steps):
            context = await self.load_context(session_id)
            if context.current_stage in {InterviewStage.LISTENING, InterviewStage.FINISHED, InterviewStage.FAILED}:
                return context
            await self.run_step(session_id)
        raise RuntimeError("Runtime step budget exhausted")

    async def _emit_artifact_event(
        self,
        context: InterviewBlackboard,
        artifact: AgentArtifact,
        previous: InterviewStage,
    ) -> None:
        mapping = {
            "candidate_profile": RuntimeEventType.PROFILE_CREATED,
            "interview_plan": RuntimeEventType.PLAN_CREATED,
            "question": RuntimeEventType.QUESTION_GENERATED,
            "evaluation": RuntimeEventType.ANSWER_EVALUATED,
            "follow_up_decision": RuntimeEventType.FOLLOW_UP_TRIGGERED,
            "interview_report": RuntimeEventType.REPORT_GENERATED,
        }
        event_type = mapping.get(artifact.kind, RuntimeEventType.CHECKPOINT_CREATED)
        await self.event_bus.emit(
            RuntimeEvent(
                event_type,
                context.session_id,
                message=artifact.kind,
                metadata={"artifact_id": artifact.id, "stage": previous.value},
            )
        )

    @staticmethod
    def _default_agents() -> InterviewAgentRegistry:
        registry = InterviewAgentRegistry()
        for agent in [ProfileAgent(), PlannerAgent(), QuestionAgent(), EvaluatorAgent(), FollowUpAgent(), ReportAgent()]:
            registry.register(agent)
        return registry


