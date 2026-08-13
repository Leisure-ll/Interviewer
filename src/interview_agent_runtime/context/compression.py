from __future__ import annotations

from dataclasses import dataclass, field

from interview_agent_runtime.blackboard import InterviewBlackboard
from interview_agent_runtime.context.builder import AgentContextBuilder
from interview_agent_runtime.memory import InterviewMemorySnapshot


class TokenEstimator:
    def estimate(self, text: str) -> int:
        return max(1, len(text) // 4)


@dataclass
class CapabilityContextCompressor:
    context_builder: AgentContextBuilder
    token_estimator: TokenEstimator = field(default_factory=TokenEstimator)

    def compress(self, blackboard: InterviewBlackboard) -> dict[str, object]:
        summary = self.snapshot(blackboard).to_dict()
        rendered = str(summary)
        summary["estimated_tokens"] = self.token_estimator.estimate(rendered)
        return summary

    def snapshot(self, blackboard: InterviewBlackboard) -> InterviewMemorySnapshot:
        return InterviewMemorySnapshot.from_blackboard(
            blackboard,
            max_evidence=self.context_builder.budget.max_evidence_items,
        )
