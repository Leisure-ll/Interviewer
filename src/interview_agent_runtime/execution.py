from __future__ import annotations

from enum import Enum


class ExecutionStrategy(str, Enum):
    """How one specialist agent completes a runtime step."""

    DETERMINISTIC = "deterministic"
    STRUCTURED_LLM = "structured_llm"
    REACT = "react"


class StopReason(str, Enum):
    COMPLETED = "completed"
    MAX_ROUNDS = "max_rounds"
    TOOL_BUDGET_EXCEEDED = "tool_budget_exceeded"
    TOKEN_BUDGET_EXCEEDED = "token_budget_exceeded"
    TIMEOUT = "timeout"
    PROVIDER_ERROR = "provider_error"
    TOOL_ERROR = "tool_error"
    REPEATED_TOOL_CALL = "repeated_tool_call"


class RuntimeOutcome(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"


__all__ = ["ExecutionStrategy", "RuntimeOutcome", "StopReason"]
