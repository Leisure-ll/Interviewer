from __future__ import annotations

import asyncio
import json

from interview_agent_runtime.blackboard import InterviewBlackboard
from interview_agent_runtime.checkpoint import JsonFileCheckpointStore
from interview_agent_runtime.memory import InMemorySessionMemory
from interview_agent_runtime.messages import AgentMessage, ToolCall
from interview_agent_runtime.providers import FakeLLMProvider
from interview_agent_runtime.runtime import AgentLoop, AgentRunRequest, RuntimeOutcome
from interview_agent_runtime.tools import (
    Tool,
    ToolContext,
    ToolExecutor,
    ToolGovernanceState,
    ToolPolicy,
    ToolRegistry,
    ToolSpec,
)


def test_parallel_safe_tools_are_parallel_and_side_effect_tools_are_serial():
    asyncio.run(_parallel_case())


async def _parallel_case():
    registry = ToolRegistry()
    active = 0
    max_active = 0

    async def read(context, args):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.01)
        active -= 1
        return {"path": args["path"]}

    registry.register(
        Tool(
            spec=ToolSpec(
                name="read_file",
                description="read",
                parallel_safe=True,
            ),
            handler=read,
        )
    )
    executor = ToolExecutor(registry, ToolPolicy({"Agent": {"read_file"}}))
    context = ToolContext("parallel", "Agent", "skill", InterviewBlackboard("parallel"))
    batch = await executor.execute_batch(
        [
            ToolCall("1", "read_file", {"path": "a"}),
            ToolCall("2", "read_file", {"path": "b"}),
        ],
        context,
        {"read_file"},
    )

    assert [item.value["path"] for item in batch.results] == ["a", "b"]
    assert batch.parallel_tool_batches == 1
    assert batch.max_parallelism == 2
    assert max_active == 2


def test_side_effect_success_is_recovered_from_json_checkpoint(tmp_path):
    asyncio.run(_recovery_case(tmp_path))


async def _recovery_case(tmp_path):
    calls = 0
    registry = ToolRegistry()

    async def send(context, args):
        nonlocal calls
        calls += 1
        return {"sent": True, "candidate_id": args["candidate_id"]}

    registry.register(
        Tool(
            spec=ToolSpec(
                name="notification.send",
                description="send",
                side_effect=True,
                idempotent=False,
            ),
            handler=send,
        )
    )
    store = JsonFileCheckpointStore(tmp_path)
    board = InterviewBlackboard("durable")
    executor = ToolExecutor(registry, ToolPolicy({"Agent": {"notification.send"}}))
    context = ToolContext("durable", "Agent", "skill", board)
    first = await executor.execute(
        ToolCall("first", "notification.send", {"candidate_id": 123}),
        context,
        {"notification.send"},
        governance=ToolGovernanceState(),
        durable_records=board.durable_tool_records,
        persist_durable_record=lambda record: _save_record(store, board, record),
        run_id="run-1",
    )
    assert first.ok
    assert calls == 1

    restored = await store.load("durable")
    assert restored is not None
    second = await executor.execute(
        ToolCall("second", "notification.send", {"candidate_id": 123}),
        context,
        {"notification.send"},
        governance=ToolGovernanceState(),
        durable_records=restored.durable_tool_records,
        run_id="run-2",
    )
    assert second.status == "durable_recovered"
    assert calls == 1


def test_same_resource_parallel_safe_calls_are_serialized():
    asyncio.run(_conflict_case())


async def _conflict_case():
    registry = ToolRegistry()
    active = 0
    max_active = 0

    async def read(context, args):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.01)
        active -= 1
        return {"path": args["path"]}

    registry.register(
        Tool(
            spec=ToolSpec(name="read_file", description="read", parallel_safe=True),
            handler=read,
        )
    )
    executor = ToolExecutor(registry, ToolPolicy({"Agent": {"read_file"}}))
    batch = await executor.execute_batch(
        [
            ToolCall("1", "read_file", {"path": "same.py"}),
            ToolCall("2", "read_file", {"path": "same.py"}),
        ],
        ToolContext("conflict", "Agent", "skill", InterviewBlackboard("conflict")),
        {"read_file"},
    )

    assert batch.resource_conflicts == 0
    assert batch.results[1].status == "duplicate_rejected"
    assert max_active == 1


def test_different_invocations_with_same_resource_are_serialized():
    asyncio.run(_resource_conflict_case())


async def _resource_conflict_case():
    registry = ToolRegistry()
    active = 0
    max_active = 0

    async def update(context, args):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.01)
        active -= 1
        return {"field": args["field"]}

    registry.register(
        Tool(
            spec=ToolSpec(
                name="candidate.update",
                description="update",
                parallel_safe=True,
            ),
            handler=update,
        )
    )
    executor = ToolExecutor(registry, ToolPolicy({"Agent": {"candidate.update"}}))
    batch = await executor.execute_batch(
        [
            ToolCall(
                "1",
                "candidate.update",
                {"candidate_id": 123, "field": "score"},
            ),
            ToolCall(
                "2",
                "candidate.update",
                {"candidate_id": 123, "field": "status"},
            ),
        ],
        ToolContext("conflict", "Agent", "skill", InterviewBlackboard("conflict")),
        {"candidate.update"},
    )

    assert [item.ok for item in batch.results] == [True, True]
    assert batch.resource_conflicts == 1
    assert batch.max_parallelism == 1
    assert max_active == 1


async def _save_record(store, board, record):
    board.durable_tool_records[record.invocation_key.fingerprint] = record
    await store.save(board)


def test_context_budget_keeps_current_task_and_domain_snapshot():
    asyncio.run(_context_case())


async def _context_case():
    provider = FakeLLMProvider(responses=[{"content": json.dumps({"done": True})}])
    registry = ToolRegistry()
    board = InterviewBlackboard("budget-boundary")
    board.current_dimension = "Redis"
    board.capability_profile.verified_skills = ["Java"]
    memory = InMemorySessionMemory()
    result = await AgentLoop(provider, memory).run(
        AgentRunRequest(
            session_id="budget-boundary",
            agent_name="EvaluatorAgent",
            skill_name="evaluate-answer",
            initial_messages=[AgentMessage.user("CURRENT QUESTION: Redis consistency")],
            visible_tools=set(),
            tool_executor=ToolExecutor(registry, ToolPolicy({"EvaluatorAgent": set()})),
            tool_context=ToolContext(
                "budget-boundary",
                "EvaluatorAgent",
                "evaluate-answer",
                board,
            ),
            blackboard=board,
            context_budget_tokens=8,
        )
    )

    assert result.stop_reason == "completed"
    contents = [item.content or "" for item in provider.requests[0].messages]
    assert any("Redis" in item for item in contents)
    assert any("CURRENT QUESTION" in item for item in contents)


def test_waiting_human_review_is_a_paused_runtime_outcome():
    assert RuntimeOutcome.PAUSED.value == "paused"
