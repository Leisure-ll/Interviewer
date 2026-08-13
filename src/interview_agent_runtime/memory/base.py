from __future__ import annotations

from typing import List, Optional, Protocol, Union

from interview_agent_runtime.messages import AgentMessage
from interview_agent_runtime.memory.models import MemoryScope

MemoryKey = Union[str, MemoryScope]


class SessionMemory(Protocol):
    async def append(self, session_id: MemoryKey, message: AgentMessage) -> None:
        ...

    async def extend(self, session_id: MemoryKey, messages: List[AgentMessage]) -> None:
        ...

    async def history(self, session_id: MemoryKey, limit: Optional[int] = None) -> List[AgentMessage]:
        ...

    async def clear(self, session_id: MemoryKey) -> None:
        ...


class MemoryCompressor(Protocol):
    async def compress(
        self,
        messages: List[AgentMessage],
        *,
        max_messages: int,
    ) -> List[AgentMessage]:
        ...
