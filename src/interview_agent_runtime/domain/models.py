from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ProjectExperience:
    name: str
    role: str = ""
    description: str = ""
    technologies: list[str] = field(default_factory=list)
    highlights: list[str] = field(default_factory=list)


@dataclass
class EducationExperience:
    school: str
    degree: str = ""
    major: str = ""
    period: str = ""


@dataclass
class CandidateProfile:
    candidate_id: str
    target_role: Optional[str] = None
    years_of_experience: Optional[float] = None
    skills: list[str] = field(default_factory=list)
    project_experiences: list[ProjectExperience] = field(default_factory=list)
    education: list[EducationExperience] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)
    possible_weaknesses: list[str] = field(default_factory=list)
    potential_gaps: list[str] = field(default_factory=list)
    resume_keywords: list[str] = field(default_factory=list)


@dataclass
class PositionProfile:
    role_name: str
    required_skills: list[str] = field(default_factory=list)
    preferred_skills: list[str] = field(default_factory=list)
    responsibilities: list[str] = field(default_factory=list)
    competency_dimensions: list[str] = field(default_factory=list)
    seniority: Optional[str] = None
    keywords: list[str] = field(default_factory=list)


@dataclass
class InterviewDimension:
    name: str
    weight: float
    target_level: str
    question_budget: int
    follow_up_budget: int
    coverage_target: float
    difficulty: str
    asked_questions: int = 0
    current_coverage: float = 0.0
    evidence_count: int = 0
    completed: bool = False


@dataclass
class InterviewPlan:
    dimensions: list[InterviewDimension]
    total_question_budget: int
    total_follow_up_budget: int
    estimated_duration_minutes: int
    current_dimension_index: int = 0

    def next_dimension(self, coverage: dict[str, float]) -> Optional[InterviewDimension]:
        for item in self.dimensions:
            item.current_coverage = max(item.current_coverage, coverage.get(item.name, 0.0))
            if item.current_coverage >= item.coverage_target:
                item.completed = True
        open_dimensions = [
            item
            for item in self.dimensions
            if not item.completed and item.question_budget > item.asked_questions
        ]
        if not open_dimensions:
            return None
        selected = sorted(
            open_dimensions,
            key=lambda item: (coverage.get(item.name, 0.0) >= item.coverage_target, -item.weight),
        )[0]
        self.current_dimension_index = self.dimensions.index(selected)
        return selected

    def mark_question_asked(self, dimension_name: str) -> None:
        for item in self.dimensions:
            if item.name == dimension_name:
                item.asked_questions += 1
                return

    def update_after_evaluation(
        self,
        dimension_name: str,
        coverage: float,
        evidence_count: int,
    ) -> int:
        """Update one dimension and return any released unused question budget."""
        for item in self.dimensions:
            if item.name != dimension_name:
                continue
            item.current_coverage = max(item.current_coverage, coverage)
            item.evidence_count += evidence_count
            if item.current_coverage >= item.coverage_target:
                item.completed = True
                released = max(0, item.question_budget - item.asked_questions)
                item.question_budget = item.asked_questions
                self._redistribute_question_budget(released, exclude=dimension_name)
                return released
            return 0
        return 0

    def _redistribute_question_budget(self, released: int, exclude: str) -> None:
        if released <= 0:
            return
        targets = [
            item
            for item in self.dimensions
            if item.name != exclude and not item.completed
        ]
        targets.sort(key=lambda item: (-item.weight, item.asked_questions))
        if targets:
            targets[0].question_budget += released

    def has_remaining_questions(self, coverage: dict[str, float]) -> bool:
        return self.next_dimension(coverage) is not None


@dataclass
class Question:
    question_id: str
    title: str
    dimension: str
    difficulty: str = "medium"
    reference_answer: str = ""
    source: str = "generated"
    tags: list[str] = field(default_factory=list)
    question_type: str = "technical"
    expected_points: list[str] = field(default_factory=list)
    related_skills: list[str] = field(default_factory=list)


@dataclass
class CapabilityProfile:
    verified_skills: list[str] = field(default_factory=list)
    weak_skills: list[str] = field(default_factory=list)
    uncertain_skills: list[str] = field(default_factory=list)
    dimension_scores: dict[str, float] = field(default_factory=dict)
    dimension_coverage: dict[str, float] = field(default_factory=dict)
    evidence_count: dict[str, int] = field(default_factory=dict)

    def update_dimension(self, dimension: str, score: float, evidence_count: int, missing_points: list[str]) -> None:
        self.dimension_scores[dimension] = score
        self.evidence_count[dimension] = self.evidence_count.get(dimension, 0) + evidence_count
        coverage_gain = 0.25 + min(0.25, evidence_count * 0.1)
        if score >= 80:
            coverage_gain += 0.2
            _append_unique(self.verified_skills, dimension)
            _remove_if_present(self.weak_skills, dimension)
            _remove_if_present(self.uncertain_skills, dimension)
        elif score < 65:
            _append_unique(self.weak_skills, dimension)
            _remove_if_present(self.verified_skills, dimension)
        elif missing_points:
            _append_unique(self.uncertain_skills, dimension)
        self.dimension_coverage[dimension] = min(1.0, self.dimension_coverage.get(dimension, 0.0) + coverage_gain)


def _append_unique(items: list[str], value: str) -> None:
    if value and value not in items:
        items.append(value)


def _remove_if_present(items: list[str], value: str) -> None:
    if value in items:
        items.remove(value)
