from __future__ import annotations

from typing import List, Optional

from interview_agent_runtime.messages import AgentMessage


class InMemorySessionMemory:
    def __init__(self) -> None:
        self._items: dict[str, list[AgentMessage]] = {}

    async def append(self, session_id: str, message: AgentMessage) -> None:
        self._items.setdefault(session_id, []).append(message)

    async def extend(self, session_id: str, messages: List[AgentMessage]) -> None:
        self._items.setdefault(session_id, []).extend(messages)

    async def history(self, session_id: str, limit: Optional[int] = None) -> List[AgentMessage]:
        messages = list(self._items.get(session_id, []))
        return messages if limit is None else messages[-limit:]

    async def clear(self, session_id: str) -> None:
        self._items.pop(session_id, None)
