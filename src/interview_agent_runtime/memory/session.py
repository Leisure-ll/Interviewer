from __future__ import annotations

from typing import List, Optional

from interview_agent_runtime.messages import AgentMessage
from interview_agent_runtime.memory.base import MemoryKey
from interview_agent_runtime.memory.models import MemoryScope


def _key(value: MemoryKey) -> str:
    return value.key() if isinstance(value, MemoryScope) else value


class InMemorySessionMemory:
    def __init__(self) -> None:
        self._items: dict[str, list[AgentMessage]] = {}

    async def append(self, session_id: MemoryKey, message: AgentMessage) -> None:
        self._items.setdefault(_key(session_id), []).append(message)

    async def extend(self, session_id: MemoryKey, messages: List[AgentMessage]) -> None:
        self._items.setdefault(_key(session_id), []).extend(messages)

    async def history(self, session_id: MemoryKey, limit: Optional[int] = None) -> List[AgentMessage]:
        messages = list(self._items.get(_key(session_id), []))
        return messages if limit is None else messages[-limit:]

    async def clear(self, session_id: MemoryKey) -> None:
        self._items.pop(_key(session_id), None)
