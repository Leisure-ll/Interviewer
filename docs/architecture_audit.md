# AI 数字人智能面试系统重构审计与设计

## 当前实现补充：Harness / Runtime / Context 边界

当前仓库已经形成收敛后的 Interview Agent Harness：

- `InterviewHarness` 负责装配 AgentRegistry、SkillRegistry、ToolPolicy、CheckpointStore、EventBus 和 `AgentContextBuilder`。
- `InterviewRuntime` 只负责单场面试执行：FSM、Agent 调度、Skill 解析、Tool 授权、Artifact 发布、Checkpoint 和 Event。
- 六个 Specialist Agent 固定为 Profile/Planner/Question/Evaluator/FollowUp/Report，不动态创建 SubAgent。
- Agent 之间不直接通信，统一通过 `Artifact -> Blackboard -> Context Projection` 协作。
- `AgentContextBuilder` 将完整 Blackboard 投影为 typed context，避免每个 Agent 默认拿全量历史。
- Context Budget 和 capability-oriented summary 已有 deterministic 实现，为后续 LLM context 控制做准备。

## 1. 当前项目架构审计

当前主项目位于 `D:\agent项目学习\数字人agent`，其中 AI 测评核心在 `harness-evaluation`。

现有能力按职责拆分如下：

| 领域 | 当前位置 | 结论 |
|---|---|---|
| Web/API | `harness_evaluation/api` | 保留，后续作为 Runtime 的外层适配器 |
| 生题服务 | `services/question_generate_service.py` | 保留业务逻辑，迁移为 QuestionAgent 的领域服务依赖 |
| 题目过滤 | `services/question_filter_service.py` | 保留，作为题库/筛选工具 |
| RAG/Qdrant | `infrastructure/qdrant`, `rag` | 保留，封装为 `question_bank.search` / `knowledge.retrieve` Tool |
| 简历画像 | `services/resume_profile_service.py` | 保留，封装为 `resume.retrieve` Tool |
| JD/岗位查询 | `infrastructure/dubbo/position_client.py` | 保留，封装为 `jd.retrieve` Tool |
| 答题流转 | `graphs/get_next_graph.py`, `graphs/submit_graph.py` | 重构，替换为 InterviewRuntime + FSM |
| 追问决策 | `infrastructure/llm/grader.py`, `graphs/nodes/submit_nodes.py` | 保留核心 prompt/判定逻辑，迁移为 FollowUpAgent |
| 评分 | `infrastructure/llm/grader.py`, `services/report_service.py` | 保留，迁移为 EvaluatorAgent / ReportAgent |
| Redis | `infrastructure/cache/redis_client.py` | 保留，作为 checkpoint/session cache 的实现之一 |
| Checkpoint | `infrastructure/checkpoint/mysql.py` | 重构，移除 LangGraph checkpointer，改为领域 CheckpointStore |
| ASR | `infrastructure/aliyun_speech`, `baidu_speech`, `speech` | 保留，作为数字人输入适配 |
| MCP/Tools | `tools/mcp_rpc.py`, `tools/database.py` | 保留工具实现，新增 ToolPolicy 和 ToolExecutor |
| Skill | `config/skills/*/SKILL.md` | 保留并增强元数据：agent/tools/schema/policy/version |
| Langfuse | `observability` / 相关集成 | 保留，专注 LLM trace；Runtime Event 单独记录业务事件 |

## 2. LangGraph 当前承担的职责

当前 LangGraph 依赖集中在：

- `graphs/workflow_graph.py`
- `graphs/chat_graph.py`
- `graphs/get_next_graph.py`
- `graphs/submit_graph.py`
- `graphs/states/*`
- `infrastructure/checkpoint/mysql.py`
- `pyproject.toml` 中 `langgraph*` 依赖

它承担了四类职责：

1. 节点编排：`load_cache -> media_parse -> decide_follow_up -> save_answer_flow`
2. 条件路由：客观题/主观题、追问/不追问、下一题/结束
3. 状态容器：TypedDict State
4. Checkpoint：MemorySaver / MySQLSaver

新架构不复刻 Graph/Node/Edge，而是将这些职责迁移为：

- FSM：领域状态迁移
- Agent：领域执行单元
- Blackboard：共享结构化状态
- Artifact：Agent 输出契约
- CheckpointStore：领域 checkpoint

## 3. K 可借鉴模块

参考项目 K 的核心启发：

| K 能力 | 设计思想 | 本项目采用方式 |
|---|---|---|
| AgentLoop | runtime 统一管理生命周期、取消、恢复、观察 | `InterviewRuntime` 管理 session step |
| FSM/Kernel | 控制循环和执行限制 | 用领域 FSM，不做通用图引擎 |
| Skill | `SKILL.md` 前置元数据 + prompt | `SkillDefinition` 增加 agent/tools/schema/policy |
| ToolRegistry | 工具定义与执行分离 | `ToolRegistry` + `ToolExecutor` |
| Tool Whitelist | 工具可见性控制 | `ToolPolicy` 做最小权限交集 |
| Memory Compression | 超长上下文压缩 | 面试能力导向压缩，不做聊天摘要 |
| Checkpoint | JSON/文件持久化 | `CheckpointStore` 协议，后续接 MySQL/Redis |
| Observer | runtime trace hooks | `EventBus` + Langfuse 关联 |

## 4. M 可借鉴模块

参考项目 M 的核心启发：

| M 能力 | 设计思想 | 本项目采用方式 |
|---|---|---|
| CollaborationBlackboard | Agent 不靠自然语言互传，而是共享结构化板 | `InterviewBlackboard` |
| AgentArtifact | 所有 Agent 输出结构化产物 | `AgentArtifact` 及子类 |
| Specialist Agent | 每个 Agent 有明确职责 | Profile/Planner/Question/Evaluator/FollowUp/Report |
| AgentDecision | Agent 先声明是否适合处理任务 | `BaseInterviewAgent.decide` |
| Coordinator | 不固定聊天顺序，管理预算和采纳 | 本项目用 Runtime + FSM，避免通用协调器复杂度 |
| Event/Audit | 每一步可审计 | `RuntimeEvent` |
| Tool Governance | 工具执行前授权 | `Agent Allowed ∩ Skill Declared ∩ Session Policy` |

## 5. 新 Interview Runtime 总体设计

核心原则：

```text
LLM 负责概率性推理，Runtime 负责确定性控制。
```

运行链路：

```text
Digital Human / Web
  -> InterviewRuntime
  -> InterviewStateMachine
  -> AgentRegistry.resolve(stage)
  -> SkillRegistry.resolve(agent.required_skill)
  -> ToolPolicy.authorize
  -> TaskExecutor.execute(timeout/retry/fallback)
  -> AgentArtifact
  -> InterviewBlackboard.publish
  -> TransitionGuard
  -> CheckpointStore.save
  -> EventBus.emit
```

当前已在 `src/interview_agent_runtime` 实现第一阶段最小闭环。

## 6. 旧 -> 新模块映射

| 旧模块 | 新模块 |
|---|---|
| `graphs/submit_graph.py` | `runtime/interview_runtime.py` + `runtime/state_machine.py` |
| `graphs/get_next_graph.py` | `QuestionAgent` + FSM |
| `graphs/answer_state.py` | `InterviewBlackboard` |
| node 函数 | `BaseInterviewAgent.execute` |
| LangGraph Checkpointer | `CheckpointStore` |
| `config/skills/*/SKILL.md` | `SkillDefinition` |
| `tools/*` | `ToolRegistry` + `ToolPolicy` |
| `question_generate_service.py` | QuestionAgent 的 service adapter |
| `grader.decide_follow_up` | FollowUpAgent |
| `grader.grade_answer` | EvaluatorAgent |
| `report_service.py` | ReportAgent |

## 7. 目录重构方案

当前新目录：

```text
AI面试/
  docs/
  src/interview_agent_runtime/
    agents/
    artifacts/
    blackboard/
    checkpoint/
    memory/
    runtime/
    skills/
    tools/
  tests/
```

后续接入旧项目时建议新增：

```text
integrations/
  existing_harness/
    question_generation_adapter.py
    grading_adapter.py
    qdrant_adapter.py
    redis_checkpoint_store.py
    mysql_checkpoint_store.py
    asr_adapter.py
```

## 8. 状态机设计

状态：

```text
INIT
PROFILE_ANALYSIS
INTERVIEW_PLANNING
QUESTION_PREPARING
QUESTIONING
LISTENING
EVALUATING
DECISION
FOLLOW_UP
NEXT_QUESTION
NEXT_DIMENSION
REPORTING
FINISHED
FAILED
```

迁移由 `InterviewStateMachine.transition()` 管理，追问通过 `TransitionGuard.allow_follow_up()` 控制。

追问必须满足：

```text
need_follow_up
confidence >= threshold
follow_up_budget > 0
question_budget > 0
target 未重复
session 未结束
```

## 9. Blackboard Schema

已实现 `InterviewBlackboard`：

- `session_id`
- `candidate_profile`
- `position_profile`
- `interview_plan`
- `current_stage`
- `current_question`
- `answers`
- `evaluations`
- `follow_up_decisions`
- `evidence`
- `dimension_scores`
- `dimension_coverage`
- `follow_up_budget`
- `question_budget`
- `token_budget`
- `asked_question_ids`
- `followed_targets`
- `runtime_metadata`

## 10. Artifact Schema

已实现：

- `CandidateProfileArtifact`
- `InterviewPlanArtifact`
- `QuestionArtifact`
- `AnswerArtifact`
- `EvaluationArtifact`
- `FollowUpDecisionArtifact`
- `Evidence`
- `InterviewReportArtifact`

Agent 不直接改状态，只返回 Artifact；Runtime 发布 Artifact 到 Blackboard。

## 11. Agent 职责

| Agent | 职责 |
|---|---|
| ProfileAgent | 简历/JD 画像准备 |
| PlannerAgent | 生成 InterviewPlan 和预算 |
| QuestionAgent | 生题、题库召回补齐、追问题生成 |
| EvaluatorAgent | 答案评分和 Evidence 抽取 |
| FollowUpAgent | 输出结构化追问决策 |
| ReportAgent | 生成 evidence-driven report |

## 12. Skill Runtime

Skill 不只是 prompt，应包含：

- name
- description
- agent
- prompt
- allowed_tools
- output_schema
- timeout
- retry
- max_tokens
- version

第一阶段在 `SkillRegistry.with_defaults()` 内置默认定义。后续迁移 `config/skills/*/SKILL.md` 时增加 frontmatter 解析。

## 13. Tool Governance

当前实现：

```text
Agent Allowed Tools
  ∩ Skill Declared Tools
  ∩ Session Policy
  = Visible Tools
```

这避免所有 Agent 都能看到所有 Tool。

示例：

- QuestionAgent：`resume.retrieve`, `jd.retrieve`, `question_bank.search`, `knowledge.retrieve`
- EvaluatorAgent：`rubric.retrieve`, `knowledge.retrieve`, `answer.semantic_match`
- ReportAgent：`evaluation.history`, `evidence.aggregate`

## 14. Question Generation Pipeline

目标迁移：

```text
Profile/JD retrieval 并行
  -> InterviewPlan
  -> Qdrant lane recall 与 LLM fan-out 并行
  -> 候选池融合
  -> quality gate
  -> dual/triple axis selection
  -> quota backfill
  -> QuestionArtifact
```

现阶段 mock `question_bank.search` 已验证题库 fallback 机制。下一步接 `question_generate_service.py` 的真实 service adapter。

## 15. Follow-up Pipeline

目标迁移：

```text
AnswerArtifact
  -> EvaluationArtifact(missing_points/evidence/confidence)
  -> FollowUpDecisionArtifact
  -> TransitionGuard
  -> FOLLOW_UP or NEXT_QUESTION
```

LLM 输出不能直接改变状态，必须经过 Guard。

## 16. Memory

设计三层：

- Working Memory：当前题、答案、评价、追问目标
- Session Memory：整场面试 evidence、覆盖度、题目历史、追问历史
- Knowledge Memory：Resume/JD/Competency/QuestionBank/Rubric/Qdrant

上下文压缩采用能力导向结构：

```json
{
  "verified_skills": [],
  "weak_skills": [],
  "uncertain_skills": [],
  "covered_dimensions": {},
  "important_evidence": []
}
```

## 17. Checkpoint

已定义：

```python
class CheckpointStore(Protocol):
    async def save(context): ...
    async def load(session_id): ...
```

第一阶段实现：

- `InMemoryCheckpointStore`
- `JsonFileCheckpointStore` 保存能力

后续实现：

- `RedisCheckpointStore`
- `MySQLCheckpointStore`

保存内容包括 Blackboard、stage、plan、budget、evidence、score、current question。

## 18. Event / Observability

自研 `EventBus` 记录业务事件：

- SESSION_STARTED
- PROFILE_CREATED
- PLAN_CREATED
- QUESTION_GENERATED
- QUESTION_ASKED
- ANSWER_RECEIVED
- ANSWER_EVALUATED
- FOLLOW_UP_TRIGGERED
- STATE_TRANSITIONED
- REPORT_GENERATED
- RUNTIME_ERROR

Langfuse 后续仍保留，职责限定为 LLM/prompt/token/latency trace。

## 19. 迁移阶段

建议渐进迁移：

1. Artifacts
2. Blackboard
3. FSM
4. InterviewRuntime
5. QuestionAgent
6. EvaluatorAgent
7. FollowUpAgent
8. ExecutionPolicy
9. Skill Runtime
10. Tool Policy
11. Memory
12. Checkpoint
13. Observer/Event

当前完成第 1-8 项的最小闭环骨架。

## 20. 第一阶段实际需要修改的文件列表

新建文件：

- `README.md`
- `pyproject.toml`
- `docs/architecture_audit.md`
- `src/interview_agent_runtime/artifacts/models.py`
- `src/interview_agent_runtime/blackboard/board.py`
- `src/interview_agent_runtime/runtime/states.py`
- `src/interview_agent_runtime/runtime/state_machine.py`
- `src/interview_agent_runtime/runtime/execution_policy.py`
- `src/interview_agent_runtime/runtime/events.py`
- `src/interview_agent_runtime/runtime/interview_runtime.py`
- `src/interview_agent_runtime/agents/base.py`
- `src/interview_agent_runtime/agents/mock_agents.py`
- `src/interview_agent_runtime/skills/registry.py`
- `src/interview_agent_runtime/tools/registry.py`
- `src/interview_agent_runtime/tools/default_tools.py`
- `src/interview_agent_runtime/checkpoint/stores.py`
- `tests/test_runtime_smoke.py`

旧项目暂不修改。下一阶段再把 `harness-evaluation` 里的真实 service 通过 adapter 接入。

## 21. 本轮 AgentLoop / Message / SessionMemory 收敛

本轮新增能力已经进入真实执行路径：

```text
InterviewRuntime
  -> Specialist Agent
  -> Skill
  -> ToolPolicy visible tools
  -> AgentLoop
  -> AgentMessage / LLMRequest
  -> assistant ToolCall
  -> ToolExecutor / ToolResult
  -> tool AgentMessage(tool_call_id)
  -> next LLM round
  -> final AgentMessage
  -> domain Artifact
  -> Blackboard
  -> FSM transition
  -> Checkpoint / Event
```

### Message Protocol

`messages/models.py` 定义：

- `MessageRole.SYSTEM`
- `MessageRole.USER`
- `MessageRole.ASSISTANT`
- `MessageRole.TOOL`
- `ToolCall`
- `AgentMessage`

`AgentMessage` 只表示单个 Agent 内部的 LLM/tool 对话。Agent 之间仍然通过：

```text
AgentArtifact -> InterviewBlackboard -> Context Projection
```

协作，不通过自然语言消息互相调用。

### LLM Provider

`LLMProvider.chat(LLMRequest)` 是主协议，`structured_generate()` 仅作为旧 Agent
兼容入口。`OpenAICompatibleLLMProvider` 支持：

- OpenAI-compatible `tools` function schema
- assistant `tool_calls`
- `tool_call_id`
- finish reason
- token usage

`FakeLLMProvider` 支持 scripted assistant/tool-call conversation，并记录每个
`LLMRequest` 的 messages 和 visible ToolSpec。

### AgentLoop

`runtime/agent_loop.py` 负责单个 Agent 的内部执行回合：

- initial messages
- SessionMemory history
- LLM request/response
- visible ToolSpec
- ToolExecutor / ToolResult
- correlated tool message
- max rounds
- max tool calls
- token budget
- timeout
- provider error stop

停止原因明确为：

```text
completed
max_rounds
tool_budget_exceeded
token_budget_exceeded
timeout
provider_error
```

### SessionMemory

`SessionMemory` 与 Blackboard 分离：

```text
SessionMemory
  = system/user/assistant/tool message history

InterviewBlackboard
  = CandidateProfile/Plan/Question/Answer/Evaluation/Evidence/Capability/Stage
```

当前提供 `InMemorySessionMemory` 和 `RecentWindowMemoryCompressor`。
`CapabilityContextCompressor` 仍然只负责面试能力域上下文，不负责通用消息历史。

### ProfileAgent 真实 Trace

Mock Harness 的 ProfileAgent 通过 AgentLoop 运行：

```text
ProfileAgent
  -> profile-analysis
  -> VisibleTools: resume.retrieve, jd.retrieve
  -> Round 1: assistant -> resume.retrieve
  -> tool: resume.retrieve result
  -> Round 2: assistant -> jd.retrieve
  -> tool: jd.retrieve result
  -> Round 3: assistant structured final
  -> CandidateProfileArtifact
  -> InterviewBlackboard
```

如果模型响应不可用或没有产出完整画像，ProfileAgent 发出
`AGENT_FALLBACK_USED`，再由 Runtime 已授权的 ToolExecutor 执行本地 fallback。

## 22. Domain-aware Memory / Trace / MCP 收敛

本轮继续保持 6 个固定 Specialist Agent 和 `Artifact -> Blackboard -> Runtime`
协作方式，只增强 Runtime 基础设施。

### Domain-aware Memory

当前 Memory 明确分三层：

```text
Interaction Memory
  = SessionMemory 中的 system/user/assistant/tool AgentMessage

Domain Working Memory
  = InterviewBlackboard 中的 Plan/Evidence/Capability/Budget/Coverage

Knowledge Memory
  = 通过 Tool Runtime 访问的 Resume/JD/QuestionBank/Rubric/RAG
```

新增：

- `MemoryScope(session_id, agent_name)`
- `InterviewMemorySnapshot`
- `MemoryContext`
- `MemoryContextBuilder`
- `DeterministicMemorySummarizer`

`AgentLoop` 现在在真实执行路径中合并：

```text
historical message summary
+ recent AgentMessage history
+ InterviewMemorySnapshot
+ current task messages
```

当前任务上下文不会因为已有历史 Memory 而丢失。ProfileAgent 仍然通过
AgentLoop 运行；其他 Agent 继续走确定性领域执行路径。

`CapabilityContextCompressor` 已复用 `InterviewMemorySnapshot`，压缩目标是能力状态，
不是普通聊天摘要。

### Run Trace

新增：

- `TraceContext`
- `RunTrace`
- `TraceSpan`
- `TraceStore`
- `InMemoryTraceStore`
- `JsonFileTraceStore`
- `TraceObserver`
- `TraceSanitizer`

Trace 通过已有 Observer 边界接入：

```text
Runtime / AgentLoop
  -> RuntimeEvent(trace=TraceContext)
  -> EventBus
  -> CompositeObserver
  -> TraceObserver
  -> TraceStore
```

Trace 层级表达为：

```text
Session trace_id
  -> Agent run_id
     -> AgentLoop span
        -> LLM span
        -> Tool span
```

`TraceSanitizer` 默认不保存完整 prompt、完整简历、完整回答、完整 messages 或完整
tool result。TraceStore 失败不会影响 CheckpointStore，Checkpoint 仍然只负责恢复快照。

### MCP Tool Adapter

新增：

- `MCPClient`
- `MCPToolDefinition`
- `MCPToolAdapter`
- `FakeMCPClient`

MCP 工具不会绕过 Runtime 的工具治理：

```text
MCP Server
  -> MCPClient
  -> MCPToolAdapter
  -> ToolSpec(source="mcp")
  -> ToolRegistry
  -> ToolPolicy
  -> visible tools
  -> AgentLoop
```

默认命名空间为 `mcp.*`，例如 `mcp.knowledge.search`。即使模型手动构造未授权
MCP ToolCall，`ToolExecutor` 仍返回失败的 `ToolResult`，不会执行 handler。

### 新增测试

- `tests/test_memory_scope.py`
- `tests/test_memory_context.py`
- `tests/test_interview_memory_snapshot.py`
- `tests/test_trace_store.py`
- `tests/test_trace_observer.py`
- `tests/test_trace_correlation.py`
- `tests/test_trace_checkpoint_boundary.py`
- `tests/test_trace_sanitizer.py`
- `tests/test_mcp_tool_adapter.py`
- `tests/test_mcp_tool_policy.py`
- `tests/test_mcp_tool_calling.py`
