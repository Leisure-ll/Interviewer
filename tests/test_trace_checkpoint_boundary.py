from __future__ import annotations

import asyncio

from interview_agent_runtime.harness import HarnessConfig, InterviewHarness
from interview_agent_runtime.observability import TraceObserver


def test_trace_store_failure_does_not_break_checkpoint_path():
    asyncio.run(_case())


class FailingTraceStore:
    async def start_trace(self, trace):
        raise RuntimeError("trace backend unavailable")

    async def append_span(self, trace_id, span):
        raise RuntimeError("trace backend unavailable")

    async def finish_span(self, trace_id, span_id, status="ok"):
        raise RuntimeError("trace backend unavailable")

    async def finish_trace(self, trace_id, status="ok"):
        raise RuntimeError("trace backend unavailable")

    async def load(self, trace_id):
        return None


async def _case():
    harness = InterviewHarness.from_config(HarnessConfig.mock())
    harness.event_bus.observer = TraceObserver(FailingTraceStore())
    runtime = harness.create_runtime("trace-failure")

    board = await runtime.start_session("trace-failure")
    restored = await runtime.load_context(board.session_id)

    assert restored.runtime_metadata.trace_id
