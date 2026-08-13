from __future__ import annotations

import asyncio

from interview_agent_runtime.observability import InMemoryTraceStore, RunTrace, TraceSpan


def test_in_memory_trace_store_persists_trace_and_span_lifecycle():
    asyncio.run(_case())


async def _case():
    store = InMemoryTraceStore()
    trace = RunTrace(trace_id="trace-1", session_id="session-1")
    span = TraceSpan(
        span_id="span-1",
        trace_id="trace-1",
        parent_span_id=None,
        name="LLM",
        kind="llm",
    )
    await store.start_trace(trace)
    await store.append_span(trace.trace_id, span)
    await store.finish_span(trace.trace_id, span.span_id)
    await store.finish_trace(trace.trace_id)

    loaded = await store.load("trace-1")
    assert loaded is not None
    assert loaded.status == "ok"
    assert loaded.finished_at is not None
    assert loaded.spans[0].status == "ok"
    assert loaded.spans[0].finished_at is not None
