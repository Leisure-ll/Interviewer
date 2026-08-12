from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Union


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
            )
        )
        return registry

    @classmethod
    def load_from_directory(cls, directory: Union[str, Path]) -> "SkillRegistry":
        registry = cls.with_defaults()
        # Phase 1 intentionally keeps parsing conservative. Existing SKILL.md files can be
        # migrated by adding frontmatter parsing here without changing runtime contracts.
        _ = Path(directory)
        return registry


