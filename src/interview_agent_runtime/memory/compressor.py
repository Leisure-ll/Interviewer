from __future__ import annotations

from typing import List

from interview_agent_runtime.messages import AgentMessage


class RecentWindowMemoryCompressor:
    async def compress(
        self,
        messages: List[AgentMessage],
        *,
        max_messages: int,
    ) -> List[AgentMessage]:
        if max_messages <= 0:
            return []
        return list(messages[-max_messages:])
