from __future__ import annotations

from dataclasses import dataclass

from interview_agent_runtime.domain import InterviewStage


@dataclass
class ExecutionContext:
    session_id: str
    current_stage: InterviewStage
    current_agent: str
    current_skill: str
    authorized_tools: set[str]
    token_budget: int
    timeout_seconds: float
    retry: int
