from __future__ import annotations

from typing import Optional, Protocol

from interview_agent_runtime.observability.sanitizer import TraceSanitizer
from interview_agent_runtime.observability.store import TraceStore
from interview_agent_runtime.observability.trace import RunTrace, TraceSpan
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


class TraceObserver:
    def __init__(
        self,
        trace_store: TraceStore,
        sanitizer: Optional[TraceSanitizer] = None,
    ) -> None:
        self.trace_store = trace_store
        self.sanitizer = sanitizer or TraceSanitizer()
        self._started_spans: set[str] = set()

    async def on_event(self, event: RuntimeEvent) -> None:
        try:
            if event.trace is None:
                return
            trace_id = event.trace.trace_id
            if event.type.value == "SESSION_STARTED":
                await self.trace_store.start_trace(
                    RunTrace(trace_id=trace_id, session_id=event.session_id)
                )
                return
            if event.type.value == "STATE_TRANSITIONED" and event.metadata.get("to") == "FINISHED":
                await self.trace_store.finish_trace(trace_id, status="ok")
            span_id = event.trace.span_id or event.trace.run_id
            if not span_id:
                return
            kind = _kind(event.type.value)
            status = "error" if event.type.value in {"TOOL_FAILED", "RUNTIME_ERROR", "AGENT_LOOP_STOPPED"} else "ok"
            if span_id not in self._started_spans:
                await self.trace_store.append_span(
                    trace_id,
                    TraceSpan(
                        span_id=span_id,
                        trace_id=trace_id,
                        parent_span_id=event.trace.parent_span_id,
                        name=event.type.value,
                        kind=kind,
                        metadata=self.sanitizer.sanitize(event.metadata),
                    ),
                )
                self._started_spans.add(span_id)
            if event.type.value in _finish_events():
                await self.trace_store.finish_span(trace_id, span_id, status=status)
        except Exception:
            # Trace is observability only; a trace backend must not break runtime correctness.
            return


def _kind(event_type: str) -> str:
    if event_type.startswith("LLM_"):
        return "llm"
    if event_type.startswith("TOOL_"):
        return "tool"
    if event_type.startswith("AGENT_"):
        return "agent"
    return "runtime"


def _finish_events() -> set[str]:
    return {
        "AGENT_FINISHED",
        "AGENT_LOOP_FINISHED",
        "AGENT_LOOP_STOPPED",
        "LLM_RESPONDED",
        "TOOL_SUCCEEDED",
        "TOOL_FAILED",
        "STATE_TRANSITIONED",
        "RUNTIME_ERROR",
    }
