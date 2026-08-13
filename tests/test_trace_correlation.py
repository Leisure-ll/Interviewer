from __future__ import annotations

import asyncio

from interview_agent_runtime.harness import HarnessConfig, InterviewHarness
from interview_agent_runtime.runtime.events import RuntimeEventType


def test_runtime_events_and_agent_loop_share_trace_and_run_ids():
    asyncio.run(_case())


async def _case():
    harness = InterviewHarness.from_config(HarnessConfig.mock())
    runtime = harness.create_runtime("trace-session")
    await runtime.start_session(
        "trace-session",
        resume={"skills": ["Java"]},
        jd={"position": "Backend", "dimensions": ["Java"]},
    )
    await runtime.run_until_waiting_or_done("trace-session", max_steps=6)

    events = runtime.event_bus.events
    trace_ids = {event.trace.trace_id for event in events if event.trace is not None}
    assert len(trace_ids) == 1
    agent_started = next(
        event for event in events if event.type == RuntimeEventType.AGENT_STARTED
    )
    loop_started = next(
        event for event in events if event.type == RuntimeEventType.AGENT_LOOP_STARTED
    )
    assert agent_started.trace is not None
    assert loop_started.trace is not None
    assert agent_started.trace.run_id == loop_started.trace.run_id
