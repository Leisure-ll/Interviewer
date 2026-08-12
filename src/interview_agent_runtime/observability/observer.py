from __future__ import annotations

from typing import Protocol

from interview_agent_runtime.runtime.events import RuntimeEvent


class Observer(Protocol):
    async def on_event(self, event: RuntimeEvent) -> None:
        ...


class NoopObserver:
    async def on_event(self, event: RuntimeEvent) -> None:
        return None


class ConsoleObserver:
    async def on_event(self, event: RuntimeEvent) -> None:
        print(f"[{event.type.value}] {event.session_id} {event.message}")


class CompositeObserver:
    def __init__(self, observers: list[Observer]) -> None:
        self.observers = observers

    async def on_event(self, event: RuntimeEvent) -> None:
        for observer in self.observers:
            await observer.on_event(event)
