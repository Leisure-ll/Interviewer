from __future__ import annotations

from typing import List, Optional, Protocol

from interview_agent_runtime.messages import AgentMessage


class SessionMemory(Protocol):
    async def append(self, session_id: str, message: AgentMessage) -> None:
        ...

    async def extend(self, session_id: str, messages: List[AgentMessage]) -> None:
        ...

    async def history(self, session_id: str, limit: Optional[int] = None) -> List[AgentMessage]:
        ...

    async def clear(self, session_id: str) -> None:
        ...


class MemoryCompressor(Protocol):
    async def compress(
        self,
        messages: List[AgentMessage],
        *,
        max_messages: int,
    ) -> List[AgentMessage]:
        ...
