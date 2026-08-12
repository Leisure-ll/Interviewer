from __future__ import annotations

import asyncio

from interview_agent_runtime.harness import HarnessConfig, InterviewHarness
from interview_agent_runtime.runtime.events import RuntimeEvent


class RecordingObserver:
    def __init__(self):
        self.events: list[RuntimeEvent] = []

    async def on_event(self, event: RuntimeEvent) -> None:
        self.events.append(event)


def test_harness_injected_observer_receives_runtime_events():
    asyncio.run(_case())


async def _case():
    observer = RecordingObserver()
    harness = InterviewHarness.from_config(HarnessConfig.mock())
    harness.observer = observer
    harness.event_bus.observer = observer
    runtime = harness.create_runtime("observer")

    board = await runtime.start_session("observer")

    assert board.session_id == "observer"
    assert observer.events
    assert observer.events[0].type.value == "SESSION_STARTED"
