# AI Interview Agent Runtime

This repository is a staged refactor target for the existing digital-human interview system.
It does not copy Kugelblitz or MindBridge code. It keeps the interview domain as the core
abstraction and removes LangGraph from the core runtime.

## Goal

Build an artifact-driven interview runtime:

```text
Harness -> Runtime -> Context Projection -> Agent -> Skill -> Authorized Tools -> Artifact -> Blackboard -> Transition -> Checkpoint/Event
```

The current phase contains a runnable AI interview loop:

```text
Start Session -> Profile -> Plan -> Generate Question -> Answer -> Evaluate -> Evidence -> Follow-up / Next Question -> Report
```

## Domain Model

The runtime is driven by interview domain objects:

- `CandidateProfile`: skills, experience, strengths, potential gaps, resume keywords.
- `PositionProfile`: role, seniority, required/preferred skills, responsibilities, dimensions, keywords.
- `InterviewPlan`: weighted dimensions, difficulty, question budget, follow-up budget, duration.
- `QuestionArtifact`: text, dimension, type, source, expected points, related skills.
- `EvaluationArtifact`: score, strengths, missing points, confidence, and evidence.
- `FollowUpDecisionArtifact`: follow-up proposal with target, reason, missing evidence, and confidence.
- `CapabilityProfile`: verified, weak, and uncertain skills with coverage and evidence counts.
- `InterviewReportArtifact`: role match score, dimension scores, evidence, recommendation.

## Local Demo

```powershell
cd D:\agent项目学习\AI面试
python scripts\demo_interview.py
```

The demo simulates a Java backend / agent engineering interview without requiring an
LLM key. It uses mock tools for resume, JD, question bank, rubric, and knowledge retrieval.
It prints the interview plan, each question, the simulated answer, evaluation evidence,
missing points, follow-up decision, transition, and final report.

## Run Tests

```powershell
cd D:\agent项目学习\AI面试
python -m pytest
```

The tests cover profile construction, planning, question generation and fallback,
evidence-driven evaluation, follow-up guard, skill loading, tool governance,
checkpoint restore, and the full interview flow.

## Current Architecture

```text
InterviewHarness
  -> providers / registries / policies / checkpoint / context builder
  -> create_runtime()
InterviewRuntime
  -> FSM / TransitionGuard
  -> ExecutionContext
  -> AgentContextBuilder
  -> Specialist Agent
  -> Skill
  -> Execution Strategy
  -> Authorized Tools
  -> Artifact
  -> Blackboard
  -> Evidence / CapabilityProfile
  -> HumanReviewPolicy
  -> Checkpoint / EventBus
```

### Execution Strategy

The six specialist agents keep a fixed topology, but they do not share one execution
mode:

- `ProfileAgent`: `react`, using `AgentLoop`, Message Protocol, SessionMemory, and tool
  calling for resume/JD exploration.
- `PlannerAgent` and `QuestionAgent`: `deterministic`, using runtime-controlled domain
  pipelines.
- `EvaluatorAgent`, `FollowUpAgent`, and `ReportAgent`: `structured_llm`, using bounded
  structured model calls where the input and output contract is stable.

`ExecutionStrategy` is separate from `InterviewStage` and `Skill`. Runtime resolves the
skill declaration first and falls back to the agent declaration.

### Tool Invocation Governance

`AgentLoop` keeps iteration and tool-call budgets separately. Each run also tracks a
canonical `ToolInvocationKey`, `ToolExecutionRecord`, cache hits, duplicate calls, and
resource-version-aware cache identity. A read-only idempotent tool may reuse a successful
result; side-effect or non-idempotent tools are never treated as ordinary cache entries.
Retryable failures remain eligible for a later retry, while repeated successful decisions
can be rejected by the duplicate guard. A single response that requests more tools than
the remaining tool budget is rejected as a batch and receives explicit tool messages.

### Human Review Gate

After `ReportArtifact` is published, the deterministic `HumanReviewPolicy` evaluates
report confidence, evidence count, dimension coverage, and optional uncertainty rules.
The result is persisted on `InterviewBlackboard`. Low-confidence or insufficient reports
enter `WAITING_HUMAN_REVIEW`; `InterviewRuntime.submit_human_review()` records the
reviewer decision and transitions to `FINISHED` or `FAILED`. Human review is a runtime
policy gate, not a seventh agent.

Core runtime remains independent from FastAPI, LangGraph, Qdrant, Redis, MySQL, ASR,
TTS, and digital-human vendors. Those systems should be connected through adapters.

## Harness / Runtime Boundary

`InterviewHarness` owns system assembly:

- mode configuration: `mock`, `development`, `production`
- agent registry
- skill registry loaded from `SKILL.md`
- tool registry and tool policy
- checkpoint store selection
- context builder and context budget
- event bus and observer
- LLM provider selection

`InterviewRuntime` owns a single interview session:

- state transition
- agent dispatch
- skill resolution
- tool authorization
- execution policy
- blackboard publishing
- checkpoint timing
- runtime events

Harness does not transition FSM state or mutate `InterviewBlackboard`.
Runtime does not scan the filesystem, build default tools, or create provider clients. It receives
those dependencies from the harness.

Default assembly lives in `harness/bootstrap.py`:

- `build_mock_harness()`: fake tools, fake LLM provider, in-memory checkpoint, no-op observer.
- `build_development_harness()`: optional OpenAI-compatible LLM provider and JSON checkpoint.
- `build_production_harness()`: OpenAI-compatible provider and JSON checkpoint boundary for now.

Production Qdrant, MySQL, Redis, and Langfuse adapters are intentionally not claimed as complete.

## Context Projection

Agents do not receive an undifferentiated prompt context. `AgentContextBuilder` projects
`InterviewBlackboard` into typed, minimal contexts:

- `ProfileAgentContext`: raw resume and JD.
- `PlannerAgentContext`: candidate, position, capability, evidence, current plan.
- `QuestionAgentContext`: current dimension, plan, capability, important evidence, recent questions.
- `EvaluationAgentContext`: current question, answer, expected points, reference, relevant evidence.
- `FollowUpAgentContext`: current question, answer, evaluation, missing points, relevant evidence,
  capability summary, follow-up history, and follow-up budget.
- `ReportAgentContext`: plan summary, capability profile, scores, key evidence, evaluation summary.

The context budget limits recent questions, recent answers, evidence items, and future
LLM context size. Capability-oriented compression keeps verified, weak, uncertain,
coverage, evidence, and unresolved gaps rather than a generic chat summary.

## Memory Architecture

Memory is deliberately split into three sources:

```text
Interaction Memory  = AgentMessage history in SessionMemory
Domain Working Memory = InterviewBlackboard, Evidence, CapabilityProfile, Plan, budgets
Knowledge Memory = resume, JD, question bank, rubric, RAG access through Tools
```

`MemoryScope(session_id, agent_name)` gives each Specialist Agent its own interaction
history. Agents share interview facts through `Artifact -> Blackboard`, not through shared
message history.

`MemoryContextBuilder` builds the K-style summary plus recent window:

```text
old AgentMessage history -> deterministic summary
recent AgentMessage history -> recent_messages
InterviewBlackboard -> InterviewMemorySnapshot
```

`InterviewMemorySnapshot` stores capability-oriented domain memory:

- verified, weak, and uncertain skills
- dimension scores and coverage
- key evidence
- unresolved gaps
- recent question ids
- current dimension

`MemoryCompressor` still only controls message history. `CapabilityContextCompressor`
now produces an `InterviewMemorySnapshot`-backed domain summary. These two compressors
remain separate because interaction history and interview capability state have different
sources of truth.

## Adaptive Interview

`PlannerAgent` builds an interview plan from candidate profile and position profile.
The plan is not static. After every evaluation, `InterviewPlanPolicy` updates dimension
coverage, marks sufficiently covered dimensions as complete, and releases unused
question budget to the remaining high-value dimensions.

`TransitionGuard` prevents the LLM/Agent output from directly controlling the flow.
Follow-up requires confidence, global budget, dimension budget, per-question round limit,
duplicate target filtering, and session timeout checks.

## Evidence-Driven Evaluation

`EvaluatorAgent` and `FollowUpAgent` are deliberately separated:

```text
Question + Answer
  -> EvaluatorAgent
  -> EvaluationArtifact(score, evidence, missing_points)
  -> Blackboard
  -> FollowUpAgent
  -> FollowUpDecisionArtifact(need_follow_up, target, reason)
  -> TransitionGuard
  -> FOLLOW_UP / NEXT_QUESTION / NEXT_DIMENSION / REPORTING
```

`EvaluationArtifact` does not contain `need_follow_up`, `follow_up_target`, or `next_state`.
Agent output is a proposal or fact; final flow control belongs to `TransitionGuard`.

`EvidenceDrivenEvaluator` does not return an isolated score. It derives:

- matched expected points
- missing points
- evidence with source question, answer excerpt, skill, confidence, and polarity
- score tied to evidence, missing points, and answer detail

`ScorePolicy` owns deterministic score aggregation so scores can be explained by matched
points, missing points, evidence confidence, and answer specificity.

The report is generated from `InterviewPlan`, `CapabilityProfile`, dimension scores,
and accumulated evidence, not from a plain chat transcript.

## LLM Provider and AgentLoop

The current code includes a typed provider boundary and a K-inspired AgentLoop:

- `AgentMessage` with `system`, `user`, `assistant`, and `tool` roles.
- `ToolCall` and correlated `tool_call_id` tool messages.
- `LLMRequest` / `LLMResponse` and `LLMProvider.chat()`.
- `FakeLLMProvider` for tests and local demo.
- `OpenAICompatibleLLMProvider` with configurable `base_url`, `api_key`, and `model`.
- OpenAI-compatible function tool schema conversion and tool-call response parsing.
- `PromptAssembler` returns initial typed `AgentMessage` values.
- `ProfileAgent`, `EvaluatorAgent`, and `FollowUpAgent` can consume structured LLM drafts.

LLM draft schemas are separate from final artifact schemas. For example, `EvaluatorAgent`
can request an `EvaluationDraft`, then `EvidenceDrivenEvaluator` and `ScorePolicy` turn
that draft into an `EvaluationArtifact`. Agents keep a deterministic fallback path when
LLM output is empty, malformed, or unavailable. Runtime/FSM/budget/guard logic is not
delegated to LLMs.

`AgentLoop` is the only component that manages one Agent's internal LLM/tool conversation:

```text
initial AgentMessage
  -> LLMResponse(assistant/tool_calls)
  -> ToolPolicy-visible ToolSpec
  -> ToolExecutor
  -> AgentMessage(role=tool, tool_call_id=...)
  -> next LLM round
  -> final AgentMessage
  -> domain Artifact
```

The loop stops on `completed`, `max_rounds`, `tool_budget_exceeded`,
`token_budget_exceeded`, `timeout`, or `provider_error`.

`SessionMemory` stores only Agent/LLM interaction messages. It is separate from
`InterviewBlackboard`, which stores interview domain facts and Artifacts. A recent-window
memory compressor is available for message history; `CapabilityContextCompressor` remains
the domain-specific capability summary compressor.

The mock Harness scripts the ProfileAgent path so the local Demo exercises:

```text
Round 1: assistant -> resume.retrieve
Round 2: assistant -> jd.retrieve
Round 3: assistant -> structured profile final
```

## Skill Runtime

`SkillRegistry.load_from_directory()` reads `skills/<name>/SKILL.md` frontmatter and
prompt text. Current skills:

- `profile-analysis`
- `interview-planning`
- `question-generation`
- `evaluate-answer`
- `follow-up-decision`
- `interview-report`

Runtime validates that the artifact class returned by an agent matches the skill
`output_schema`. For example, `evaluate-answer` must return `EvaluationArtifact`.

## Tool Governance

Tools remain behind `ToolRegistry`, `ToolSpec`, `ToolExecutor`, and `ToolPolicy`. Agent
visible tools are computed by:

```text
Agent allowed tools ∩ Skill declared tools ∩ Session policy
```

The default tools are fake adapters for local execution. Real Qdrant, MySQL, Redis,
LLM, ASR, TTS, and digital-human integrations should be connected as adapters.

`ToolExecutor` returns `ToolResult` with `tool_call_id`, `tool_name`, success state,
value/error, and duration. Unauthorized ToolCalls are rejected even if proposed by
the model.

MCP tools are adapted into the same runtime model instead of creating a second tool
system:

```text
MCPClient -> MCPToolAdapter -> ToolSpec(source="mcp") -> ToolRegistry -> ToolPolicy -> AgentLoop
```

`FakeMCPClient` is available for tests. MCP tools are namespaced by default, for example
`mcp.knowledge.search`, and still require the normal three-way authorization intersection
before the model can see or execute them.

## Trace / Observer

Runtime events now carry a typed `TraceContext` with `trace_id`, `run_id`, `span_id`,
and `parent_span_id`. The trace hierarchy is intentionally small:

```text
Interview Session Trace
  -> Agent Run
     -> AgentLoop
        -> LLM Call
        -> Tool Call
```

`TraceObserver` listens to `RuntimeEvent` through the existing observer boundary and writes
to a `TraceStore`. Implementations currently include `InMemoryTraceStore` and
`JsonFileTraceStore`. `TraceSanitizer` keeps sensitive fields such as prompts, raw resume,
full answers, messages, and tool results out of trace metadata by default.

Checkpoint and trace are separate:

```text
CheckpointStore = recovery snapshot
TraceStore = observability timeline
```

Trace failures are swallowed inside `TraceObserver` so observability backends do not break
blackboard checkpointing or interview execution.

## Architecture Sources

The implementation is inspired by, but does not copy, the two reference architectures:

- Kugelblitz-inspired: AgentLoop, visible tool whitelist, Skill/Tool runtime,
  execution limits, SessionMemory, memory context, MCP tool adapter, Checkpoint, and Observer.
- MindBridge-inspired: typed AgentMessage for internal LLM communication,
  Specialist Agent, Artifact, Blackboard, and structured collaboration.
- Interviewer-owned domain: Interview FSM, InterviewPlan, Evidence, CapabilityProfile,
  InterviewMemorySnapshot, adaptive follow-up, and evidence-driven reporting.

`AgentMessage` is internal to one AgentLoop. Specialist Agents still collaborate only
through `Artifact -> Blackboard -> Context Projection`; messages are not an Agent-to-Agent
communication protocol.

## Checkpoint Recovery

`JsonFileCheckpointStore` supports save/load of the interview blackboard, including:

- session inputs
- current stage and question
- candidate and position profiles
- interview plan
- answers, evaluations, evidence
- capability profile
- budget and follow-up state

## Application Service

`InterviewApplicationService` is the intended entry point for API, web, or digital-human
interaction layers:

- `start_interview(candidate_id, resume, jd)`
- `submit_answer(session_id, answer)`
- `resume_interview(session_id)`
- `get_status(session_id)`
- `get_report(session_id)`
