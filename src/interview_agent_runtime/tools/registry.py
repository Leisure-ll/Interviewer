from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, Optional

from interview_agent_runtime.blackboard import InterviewBlackboard
from interview_agent_runtime.skills import SkillDefinition


@dataclass
class ToolContext:
    session_id: str
    agent_name: str
    skill_name: str
    blackboard: InterviewBlackboard


ToolHandler = Callable[[ToolContext, Dict[str, Any]], Awaitable[Dict[str, Any]]]


@dataclass
class Tool:
    name: str
    description: str
    handler: ToolHandler
    metadata: dict[str, Any] = field(default_factory=dict)


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def resolve(self, name: str) -> Tool:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise KeyError(f"Tool not registered: {name}") from exc

    def names(self) -> set[str]:
        return set(self._tools)


class ToolPolicy:
    def __init__(self, agent_allowed_tools: Optional[dict[str, set[str]]] = None) -> None:
        self.agent_allowed_tools = agent_allowed_tools or {
            "ProfileAgent": {"resume.retrieve", "jd.retrieve"},
            "PlannerAgent": {"jd.retrieve", "rubric.retrieve"},
            "QuestionAgent": {"resume.retrieve", "jd.retrieve", "question_bank.search", "knowledge.retrieve"},
            "EvaluatorAgent": {"rubric.retrieve", "knowledge.retrieve", "answer.semantic_match"},
            "FollowUpAgent": {"rubric.retrieve", "knowledge.retrieve"},
            "ReportAgent": {"evaluation.history", "evidence.aggregate"},
        }

    def authorize(
        self,
        agent_name: str,
        skill: SkillDefinition,
        session_allowed_tools: Optional[set[str]] = None,
    ) -> set[str]:
        allowed = set(self.agent_allowed_tools.get(agent_name, set()))
        declared = set(skill.allowed_tools)
        session = session_allowed_tools if session_allowed_tools is not None else allowed | declared
        return allowed & declared & session


class ToolExecutor:
    def __init__(self, registry: ToolRegistry, policy: ToolPolicy) -> None:
        self.registry = registry
        self.policy = policy

    async def call(
        self,
        tool_name: str,
        args: dict[str, Any],
        context: ToolContext,
        visible_tools: set[str],
    ) -> dict[str, Any]:
        if tool_name not in visible_tools:
            raise PermissionError(f"Tool not authorized for {context.agent_name}: {tool_name}")
        tool = self.registry.resolve(tool_name)
        return await tool.handler(context, args)


