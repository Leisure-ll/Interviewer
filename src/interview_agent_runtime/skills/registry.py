from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Union

from interview_agent_runtime.execution import ExecutionStrategy


@dataclass
class SkillDefinition:
    name: str
    description: str = ""
    agent: str = ""
    prompt: str = ""
    allowed_tools: list[str] = field(default_factory=list)
    output_schema: str = ""
    timeout: float = 15.0
    retry: int = 0
    max_tokens: int = 2500
    version: str = "1.0"
    execution_strategy: Optional[ExecutionStrategy] = None
    max_iterations: int = 4
    max_tool_calls: int = 8
    max_duplicate_calls: int = 1


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: dict[str, SkillDefinition] = {}

    def register(self, skill: SkillDefinition) -> None:
        self._skills[skill.name] = skill

    def resolve(self, name: str) -> SkillDefinition:
        try:
            return self._skills[name]
        except KeyError as exc:
            raise KeyError(f"Skill not registered: {name}") from exc

    def list_names(self) -> list[str]:
        return sorted(self._skills)

    @classmethod
    def with_defaults(cls) -> "SkillRegistry":
        registry = cls()
        registry.register(
            SkillDefinition(
                name="profile-analysis",
                description="Build candidate profile from resume and JD.",
                agent="ProfileAgent",
                allowed_tools=["resume.retrieve", "jd.retrieve"],
                output_schema="CandidateProfileArtifact",
                timeout=8,
                retry=1,
                execution_strategy=ExecutionStrategy.REACT,
            )
        )
        registry.register(
            SkillDefinition(
                name="interview-planning",
                description="Build an interview plan from competency dimensions.",
                agent="PlannerAgent",
                allowed_tools=["jd.retrieve", "rubric.retrieve"],
                output_schema="InterviewPlanArtifact",
                timeout=8,
                retry=1,
                execution_strategy=ExecutionStrategy.DETERMINISTIC,
            )
        )
        registry.register(
            SkillDefinition(
                name="question-generation",
                description="Generate or retrieve interview questions.",
                agent="QuestionAgent",
                allowed_tools=["question_bank.search", "knowledge.retrieve", "resume.retrieve", "jd.retrieve"],
                output_schema="QuestionArtifact",
                timeout=15,
                retry=1,
                execution_strategy=ExecutionStrategy.DETERMINISTIC,
            )
        )
        registry.register(
            SkillDefinition(
                name="evaluate-answer",
                description="Evaluate candidate answer and extract evidence.",
                agent="EvaluatorAgent",
                allowed_tools=["rubric.retrieve", "knowledge.retrieve", "answer.semantic_match"],
                output_schema="EvaluationArtifact",
                timeout=15,
                retry=1,
                execution_strategy=ExecutionStrategy.STRUCTURED_LLM,
            )
        )
        registry.register(
            SkillDefinition(
                name="follow-up-decision",
                description="Decide if a follow-up is needed.",
                agent="FollowUpAgent",
                allowed_tools=["rubric.retrieve", "knowledge.retrieve"],
                output_schema="FollowUpDecisionArtifact",
                timeout=2,
                retry=0,
                execution_strategy=ExecutionStrategy.STRUCTURED_LLM,
            )
        )
        registry.register(
            SkillDefinition(
                name="interview-report",
                description="Create evidence-driven interview report.",
                agent="ReportAgent",
                allowed_tools=["evaluation.history", "evidence.aggregate"],
                output_schema="InterviewReportArtifact",
                timeout=20,
                retry=1,
                execution_strategy=ExecutionStrategy.STRUCTURED_LLM,
            )
        )
        return registry

    @classmethod
    def load_from_directory(cls, directory: Union[str, Path]) -> "SkillRegistry":
        registry = cls.with_defaults()
        root = Path(directory)
        if not root.exists():
            return registry
        for path in root.rglob("SKILL.md"):
            skill = _parse_skill_markdown(path)
            registry.register(skill)
        return registry


def _parse_skill_markdown(path: Path) -> SkillDefinition:
    text = path.read_text(encoding="utf-8")
    frontmatter: dict[str, Any] = {}
    prompt = text
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            raw = text[3:end].strip()
            prompt = text[end + 4 :].strip()
            frontmatter = _parse_frontmatter(raw)
    return SkillDefinition(
        name=str(frontmatter.get("name") or path.parent.name),
        description=str(frontmatter.get("description", "")),
        agent=str(frontmatter.get("agent", "")),
        prompt=prompt,
        allowed_tools=list(frontmatter.get("tools", [])),
        output_schema=str(frontmatter.get("output_schema", "")),
        timeout=float(frontmatter.get("timeout", 15)),
        retry=int(frontmatter.get("retry", 0)),
        max_tokens=int(frontmatter.get("max_tokens", 2500)),
        version=str(frontmatter.get("version", "1.0")),
        execution_strategy=_parse_execution_strategy(frontmatter.get("execution_strategy")),
        max_iterations=int(frontmatter.get("max_iterations", 4)),
        max_tool_calls=int(frontmatter.get("max_tool_calls", 8)),
        max_duplicate_calls=int(frontmatter.get("max_duplicate_calls", 1)),
    )


def _parse_frontmatter(raw: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    current_key = ""
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("- ") and current_key:
            data.setdefault(current_key, []).append(stripped[2:].strip())
            continue
        if ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        current_key = key.strip()
        value = value.strip()
        if value == "":
            data[current_key] = []
        elif value.isdigit():
            data[current_key] = int(value)
        else:
            try:
                data[current_key] = float(value)
            except ValueError:
                data[current_key] = value.strip('"').strip("'")
    return data


def _parse_execution_strategy(value: Any) -> Optional[ExecutionStrategy]:
    if value in (None, ""):
        return None
    return ExecutionStrategy(str(value))


