from __future__ import annotations

from typing import Optional

from interview_agent_runtime.blackboard import InterviewBlackboard
from interview_agent_runtime.messages import AgentMessage
from interview_agent_runtime.memory.base import MemoryCompressor, SessionMemory
from interview_agent_runtime.memory.compressor import DeterministicMemorySummarizer
from interview_agent_runtime.memory.models import (
    InterviewMemorySnapshot,
    MemoryContext,
    MemoryScope,
)


class MemoryContextBuilder:
    """Builds interaction history and domain memory without merging their sources."""

    def __init__(
        self,
        memory: SessionMemory,
        *,
        compressor: Optional[MemoryCompressor] = None,
        summarizer: Optional[DeterministicMemorySummarizer] = None,
        snapshot_builder: Optional[CapabilityMemorySnapshotBuilder] = None,
    ) -> None:
        self.memory = memory
        self.compressor = compressor
        self.summarizer = summarizer or DeterministicMemorySummarizer()
        self.snapshot_builder = snapshot_builder or CapabilityMemorySnapshotBuilder()

    async def build(
        self,
        scope: MemoryScope,
        *,
        blackboard: Optional[InterviewBlackboard] = None,
        max_recent_messages: int = 12,
        max_summary_messages: int = 20,
    ) -> MemoryContext:
        history = await self.memory.history(scope.key())
        recent = list(history[-max_recent_messages:]) if max_recent_messages > 0 else []
        older = history[:-max_recent_messages] if max_recent_messages > 0 else history
        if self.compressor is not None and recent:
            recent = await self.compressor.compress(
                recent,
                max_messages=max_recent_messages,
            )
        summary = None
        if older:
            summary = self.summarizer.summarize(older[-max_summary_messages:])
        snapshot = (
            self.snapshot_builder.build(blackboard)
            if blackboard is not None
            else None
        )
        return MemoryContext(
            summary=summary,
            recent_messages=recent,
            domain_snapshot=snapshot,
        )


class CapabilityMemorySnapshotBuilder:
    def build(self, blackboard: InterviewBlackboard) -> InterviewMemorySnapshot:
        return InterviewMemorySnapshot.from_blackboard(blackboard)
