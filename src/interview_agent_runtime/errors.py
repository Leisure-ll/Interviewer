class AgentRuntimeError(RuntimeError):
    pass


class LLMProviderError(AgentRuntimeError):
    pass


class ToolError(AgentRuntimeError):
    pass


class ToolPermissionError(ToolError):
    pass


class ToolExecutionError(ToolError):
    pass


class ToolTimeoutError(ToolError):
    pass


class ToolDurabilityError(ToolError):
    pass


class AgentLoopError(AgentRuntimeError):
    pass


class AgentLoopBudgetExceeded(AgentLoopError):
    pass
