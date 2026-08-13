from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional
from uuid import uuid4

from interview_agent_runtime.agents import AgentRunContext, InterviewAgentRegistry
from interview_agent_runtime.artifacts import AgentArtifact, AnswerArtifact
from interview_agent_runtime.blackboard import InterviewBlackboard
from interview_agent_runtime.checkpoint import CheckpointStore
from interview_agent_runtime.context import AgentContextBuilder, ExecutionContext
from interview_agent_runtime.memory import MemoryCompressor, SessionMemory
from interview_agent_runtime.memory import MemoryScope
from interview_agent_runtime.providers import LLMProvider
from interview_agent_runtime.runtime.agent_loop import AgentLoop
from interview_agent_runtime.runtime.events import (
    InMemoryEventBus,
    RuntimeEvent,
    RuntimeEventType,
    TraceContext,
)
from interview_agent_runtime.runtime.execution_policy import ExecutionPolicy, TaskExecutor
from interview_agent_runtime.runtime.state_machine import InterviewStateMachine
from interview_agent_runtime.domain import InterviewStage
from interview_agent_runtime.skills import SkillRegistry
from interview_agent_runtime.tools import ToolExecutor, ToolPolicy, ToolRegistry


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
        state_machine: InterviewStateMachine,
        agent_registry: InterviewAgentRegistry,
        skill_registry: SkillRegistry,
        tool_registry: ToolRegistry,
        tool_policy: ToolPolicy,
        checkpoint_store: CheckpointStore,
        event_bus: InMemoryEventBus,
        executor: TaskExecutor,
        context_builder: AgentContextBuilder,
        memory: Optional[SessionMemory] = None,
        llm_provider: Optional[LLMProvider] = None,
        memory_compressor: Optional[MemoryCompressor] = None,
    ) -> None:
        self.state_machine = state_machine
        self.agent_registry = agent_registry
        self.skill_registry = skill_registry
        self.tool_registry = tool_registry
        self.tool_policy = tool_policy
        self.tool_executor = ToolExecutor(self.tool_registry, self.tool_policy)
        self.checkpoint_store = checkpoint_store
        self.event_bus = event_bus
        self.executor = executor
        self.context_builder = context_builder
        self.memory = memory
        self.llm_provider = llm_provider
        self.agent_loop = (
            AgentLoop(llm_provider, memory, event_bus, memory_compressor)
            if llm_provider is not None and memory is not None
            else None
        )

    async def start_session(
        self,
        session_id: Optional[str] = None,
        *,
        resume: Optional[dict[str, Any]] = None,
        jd: Optional[dict[str, Any]] = None,
        candidate_id: Optional[str] = None,
        session_allowed_tools: Optional[set[str]] = None,
    ) -> InterviewBlackboard:
        board = InterviewBlackboard(session_id=session_id or f"session_{uuid4().hex[:12]}")
        board.runtime_metadata.trace_id = f"trace_{uuid4().hex[:16]}"
        self.event_bus.bind_trace(
            board.session_id,
            TraceContext(trace_id=board.runtime_metadata.trace_id),
        )
        board.session_inputs = {
            "resume": resume or {},
            "jd": jd or {},
            "candidate_id": candidate_id,
        }
        board.session_allowed_tools = (
            set(session_allowed_tools) if session_allowed_tools is not None else None
        )
        await self.checkpoint_store.save(board)
        await self.event_bus.emit(RuntimeEvent(RuntimeEventType.SESSION_STARTED, board.session_id))
        return board

    async def load_context(self, session_id: str) -> InterviewBlackboard:
        context = await self.checkpoint_store.load(session_id)
        if context is None:
            raise KeyError(f"Session not found: {session_id}")
        return context

    async def receive_answer(
        self,
        session_id: str,
        text: str,
        *,
        source: str = "text",
        duration_seconds: Optional[float] = None,
    ) -> RuntimeStepResult:
        context = await self.load_context(session_id)
        self.event_bus.bind_trace(
            session_id,
            TraceContext(trace_id=context.runtime_metadata.trace_id),
        )
        if context.current_stage != InterviewStage.LISTENING:
            raise RuntimeError(f"Session is not listening: {context.current_stage.value}")
        if context.current_question is None:
            raise RuntimeError("No current question")
        artifact = AnswerArtifact(
            owner="Candidate",
            question_id=context.current_question.question_id,
            text=text,
            source=source,
            duration_seconds=duration_seconds,
        )
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
        self.event_bus.bind_trace(
            session_id,
            TraceContext(trace_id=context.runtime_metadata.trace_id),
        )
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
        visible_tools = self.tool_policy.authorize(
            agent.name,
            skill,
            context.session_allowed_tools,
        )
        policy = ExecutionPolicy(timeout_seconds=skill.timeout, retry=skill.retry, name=f"{agent.name}:{skill.name}")
        execution_context = ExecutionContext(
            session_id=session_id,
            current_stage=previous,
            current_agent=agent.name,
            current_skill=skill.name,
            authorized_tools=visible_tools,
            token_budget=skill.max_tokens,
            timeout_seconds=skill.timeout,
            retry=skill.retry,
            session_allowed_tools=context.session_allowed_tools,
        )
        agent_context = self.context_builder.build(agent.name, context, execution_context)
        run_id = f"run_{uuid4().hex[:12]}"
        run_trace = TraceContext(
            trace_id=context.runtime_metadata.trace_id,
            run_id=run_id,
            span_id=run_id,
        )
        self.event_bus.bind_trace(session_id, run_trace)
        await self.event_bus.emit(
            RuntimeEvent(
                RuntimeEventType.AGENT_STARTED,
                session_id,
                metadata={
                    "agent": agent.name,
                    "stage": previous.value,
                    "skill": skill.name,
                    "context_type": type(agent_context).__name__,
                    "authorized_tools": sorted(visible_tools),
                },
                trace=run_trace,
            )
        )

        run_context = AgentRunContext(
            session_id=session_id,
            blackboard=context,
            agent_context=agent_context,
            skill=skill,
            visible_tools=visible_tools,
            token_budget=skill.max_tokens,
            timeout_seconds=skill.timeout,
            retry=skill.retry,
            tools=self.tool_executor,
            agent_loop=self.agent_loop,
            event_bus=self.event_bus,
            trace=run_trace,
            memory_scope=MemoryScope(session_id, agent.name),
        )
        result = await self.executor.execute(lambda: agent.execute_run(run_context), policy)
        if not result.ok or result.value is None:
            context.runtime_metadata.errors.append(str(result.error))
            context.current_stage = InterviewStage.FAILED
            await self.checkpoint_store.save(context)
            await self.event_bus.emit(RuntimeEvent(RuntimeEventType.RUNTIME_ERROR, session_id, message=str(result.error)))
            return RuntimeStepResult(session_id, previous, context.current_stage, None)

        artifact = result.value
        self._validate_artifact_schema(artifact, skill.output_schema)
        context.publish(artifact)
        context.current_stage = self.state_machine.transition(previous, context, artifact)

        await self.checkpoint_store.save(context)
        await self._emit_artifact_event(context, artifact, previous)
        await self.event_bus.emit(
            RuntimeEvent(
                RuntimeEventType.AGENT_FINISHED,
                session_id,
                metadata={"agent": agent.name, "stage": previous.value, "artifact": artifact.kind},
            )
        )
        await self.event_bus.emit(
            RuntimeEvent(
                RuntimeEventType.STATE_TRANSITIONED,
                session_id,
                metadata={"from": previous.value, "to": context.current_stage.value, "artifact": artifact.kind},
            )
        )
        self.event_bus.bind_trace(
            session_id,
            TraceContext(trace_id=context.runtime_metadata.trace_id),
        )
        return RuntimeStepResult(session_id, previous, context.current_stage, artifact)

    def _validate_artifact_schema(self, artifact: AgentArtifact, output_schema: str) -> None:
        if not output_schema:
            return
        if type(artifact).__name__ != output_schema:
            raise TypeError(
                f"Skill output schema mismatch: expected {output_schema}, got {type(artifact).__name__}"
            )

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
            "follow_up_decision": RuntimeEventType.FOLLOW_UP_DECIDED,
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
