from __future__ import annotations

import asyncio

from interview_agent_runtime.observability import InMemoryTraceStore, TraceObserver
from interview_agent_runtime.runtime.events import (
    RuntimeEvent,
    RuntimeEventType,
    TraceContext,
)


def test_trace_observer_builds_correlated_span_from_runtime_events():
    asyncio.run(_case())


async def _case():
    store = InMemoryTraceStore()
    observer = TraceObserver(store)
    trace = TraceContext(
        trace_id="trace-observer",
        run_id="run-1",
        span_id="llm-1",
        parent_span_id="loop-1",
    )

    await observer.on_event(
        RuntimeEvent(
            RuntimeEventType.SESSION_STARTED,
            "session-observer",
            trace=TraceContext(trace_id="trace-observer"),
        )
    )
    await observer.on_event(
        RuntimeEvent(
            RuntimeEventType.LLM_REQUESTED,
            "session-observer",
            metadata={"agent": "ProfileAgent", "prompt": "secret"},
            trace=trace,
        )
    )
    await observer.on_event(
        RuntimeEvent(
            RuntimeEventType.LLM_RESPONDED,
            "session-observer",
            metadata={"agent": "ProfileAgent", "total_tokens": 12},
            trace=trace,
        )
    )

    loaded = await store.load("trace-observer")
    assert loaded is not None
    assert len(loaded.spans) == 1
    assert loaded.spans[0].parent_span_id == "loop-1"
    assert loaded.spans[0].status == "ok"
    assert "prompt" not in loaded.spans[0].metadata
    assert loaded.spans[0].metadata["prompt_length"] == len("secret")
