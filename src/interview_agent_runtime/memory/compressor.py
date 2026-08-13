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


class DeterministicMemorySummarizer:
    """Small deterministic summary for old interaction messages.

    It is intentionally not a domain summarizer. Interview capability state is
    represented separately by InterviewMemorySnapshot.
    """

    def summarize(self, messages: List[AgentMessage]) -> AgentMessage:
        lines: list[str] = []
        for message in messages:
            content = (message.content or "").strip().replace("\n", " ")
            if len(content) > 160:
                content = content[:157] + "..."
            tool_names = ",".join(call.name for call in message.tool_calls)
            suffix = f" tools={tool_names}" if tool_names else ""
            lines.append(f"{message.role.value}:{content}{suffix}".strip())
        return AgentMessage.system(
            "Earlier interaction history summary:\n" + "\n".join(lines)
        )
