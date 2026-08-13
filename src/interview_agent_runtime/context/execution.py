from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Set

from interview_agent_runtime.domain import InterviewStage
from interview_agent_runtime.execution import ExecutionStrategy


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
    session_allowed_tools: Optional[Set[str]] = None
    execution_strategy: ExecutionStrategy = ExecutionStrategy.STRUCTURED_LLM
