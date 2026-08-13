from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Protocol, Union

from interview_agent_runtime.artifacts import (
    AnswerArtifact,
    CandidateProfileArtifact,
    EvaluationArtifact,
    Evidence,
    FollowUpDecisionArtifact,
    InterviewPlanArtifact,
    InterviewReportArtifact,
    QuestionArtifact,
)
from interview_agent_runtime.blackboard import InterviewBlackboard, RuntimeMetadata
from interview_agent_runtime.domain import (
    CapabilityProfile,
    CandidateProfile,
    EducationExperience,
    InterviewDimension,
    InterviewPlan,
    InterviewStage,
    PositionProfile,
    ProjectExperience,
)


class CheckpointStore(Protocol):
    async def save(self, context: InterviewBlackboard) -> None:
        ...

    async def load(self, session_id: str) -> Optional[InterviewBlackboard]:
        ...


class InMemoryCheckpointStore:
    def __init__(self) -> None:
        self._items: dict[str, InterviewBlackboard] = {}

    async def save(self, context: InterviewBlackboard) -> None:
        self._items[context.session_id] = context

    async def load(self, session_id: str) -> Optional[InterviewBlackboard]:
        return self._items.get(session_id)


class JsonFileCheckpointStore:
    def __init__(self, root: Union[str, Path]) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    async def save(self, context: InterviewBlackboard) -> None:
        path = self.root / f"{context.session_id}.json"
        path.write_text(json.dumps(_to_json(context), ensure_ascii=False, indent=2), encoding="utf-8")

    async def load(self, session_id: str) -> Optional[InterviewBlackboard]:
        path = self.root / f"{session_id}.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return _blackboard_from_json(data)


def _blackboard_from_json(data: dict[str, Any]) -> InterviewBlackboard:
    board = InterviewBlackboard(session_id=data["session_id"])
    board.session_inputs = dict(data.get("session_inputs", {}))
    board.current_stage = InterviewStage(data.get("current_stage", InterviewStage.INIT.value))
    board.current_dimension = data.get("current_dimension", "")
    board.position_profile = _position(data.get("position_profile"))
    board.candidate_profile = _candidate_artifact(data.get("candidate_profile"))
    board.interview_plan = _plan_artifact(data.get("interview_plan"))
    board.current_question = _question(data.get("current_question"))
    board.question_history = [_question(item) for item in data.get("question_history", []) if item]
    board.answers = [_answer(item) for item in data.get("answers", [])]
    board.evaluations = [_evaluation(item) for item in data.get("evaluations", [])]
    board.follow_up_decisions = [_follow_up(item) for item in data.get("follow_up_decisions", [])]
    board.report = _report(data.get("report"))
    board.evidence = [_evidence(item) for item in data.get("evidence", [])]
    board.capability_profile = _capability(data.get("capability_profile", {}))
    board.follow_up_budget = data.get("follow_up_budget", 0)
    board.question_budget = data.get("question_budget", 0)
    board.token_budget = data.get("token_budget", 0)
    allowed_tools = data.get("session_allowed_tools")
    board.session_allowed_tools = set(allowed_tools) if allowed_tools is not None else None
    board.asked_question_ids = set(data.get("asked_question_ids", []))
    board.followed_targets = set(data.get("followed_targets", []))
    board.question_follow_up_rounds = dict(data.get("question_follow_up_rounds", {}))
    board.runtime_metadata = _runtime_metadata(data.get("runtime_metadata", {}))
    return board


def _candidate_artifact(data: Optional[dict[str, Any]]) -> Optional[CandidateProfileArtifact]:
    if not data:
        return None
    artifact = CandidateProfileArtifact(
        owner=data.get("owner", "ProfileAgent"),
        candidate_profile=_candidate(data.get("candidate_profile", {})),
        position_profile=_position(data.get("position_profile")),
        resume_id=data.get("resume_id", ""),
        confidence=data.get("confidence", 1.0),
    )
    _copy_base(artifact, data)
    return artifact


def _candidate(data: dict[str, Any]) -> CandidateProfile:
    return CandidateProfile(
        candidate_id=data.get("candidate_id", "candidate"),
        target_role=data.get("target_role"),
        years_of_experience=data.get("years_of_experience"),
        skills=list(data.get("skills", [])),
        project_experiences=[ProjectExperience(**item) for item in data.get("project_experiences", [])],
        education=[EducationExperience(**item) for item in data.get("education", [])],
        strengths=list(data.get("strengths", [])),
        possible_weaknesses=list(data.get("possible_weaknesses", [])),
        potential_gaps=list(data.get("potential_gaps", [])),
        resume_keywords=list(data.get("resume_keywords", [])),
    )


def _position(data: Optional[dict[str, Any]]) -> Optional[PositionProfile]:
    if not data:
        return None
    return PositionProfile(
        role_name=data.get("role_name", "Software Engineer"),
        required_skills=list(data.get("required_skills", [])),
        preferred_skills=list(data.get("preferred_skills", [])),
        responsibilities=list(data.get("responsibilities", [])),
        competency_dimensions=list(data.get("competency_dimensions", [])),
        seniority=data.get("seniority"),
        keywords=list(data.get("keywords", [])),
    )


def _plan_artifact(data: Optional[dict[str, Any]]) -> Optional[InterviewPlanArtifact]:
    if not data:
        return None
    artifact = InterviewPlanArtifact(owner=data.get("owner", "PlannerAgent"), plan=_plan(data.get("plan", {})))
    _copy_base(artifact, data)
    return artifact


def _plan(data: dict[str, Any]) -> InterviewPlan:
    dimensions = [InterviewDimension(**item) for item in data.get("dimensions", [])]
    return InterviewPlan(
        dimensions=dimensions,
        total_question_budget=data.get("total_question_budget", sum(item.question_budget for item in dimensions)),
        total_follow_up_budget=data.get("total_follow_up_budget", sum(item.follow_up_budget for item in dimensions)),
        estimated_duration_minutes=data.get("estimated_duration_minutes", 0),
        current_dimension_index=data.get("current_dimension_index", 0),
    )


def _question(data: Optional[dict[str, Any]]) -> Optional[QuestionArtifact]:
    if not data:
        return None
    artifact = QuestionArtifact(
        owner=data.get("owner", "QuestionAgent"),
        question_id=data.get("question_id", ""),
        title=data.get("title", ""),
        dimension=data.get("dimension", ""),
        description=data.get("description", ""),
        text=data.get("text"),
        difficulty=data.get("difficulty", "medium"),
        question_type=data.get("question_type", "technical"),
        reference_answer=data.get("reference_answer", ""),
        source=data.get("source", "llm"),
        is_follow_up=data.get("is_follow_up", False),
        target_evidence=list(data.get("target_evidence", [])),
        expected_points=list(data.get("expected_points", [])),
        related_skills=list(data.get("related_skills", [])),
        tags=list(data.get("tags", [])),
        parent_question_id=data.get("parent_question_id"),
    )
    _copy_base(artifact, data)
    return artifact


def _answer(data: dict[str, Any]) -> AnswerArtifact:
    artifact = AnswerArtifact(
        owner=data.get("owner", "Candidate"),
        question_id=data.get("question_id", ""),
        text=data.get("text", ""),
        source=data.get("source", "text"),
        duration_seconds=data.get("duration_seconds"),
    )
    artifact.answer_id = data.get("answer_id", artifact.answer_id)
    artifact.normalized_text = data.get("normalized_text", artifact.normalized_text)
    _copy_base(artifact, data)
    return artifact


def _evaluation(data: dict[str, Any]) -> EvaluationArtifact:
    artifact = EvaluationArtifact(
        owner=data.get("owner", "EvaluatorAgent"),
        question_id=data.get("question_id", ""),
        answer_id=data.get("answer_id", ""),
        score=data.get("score", data.get("overall_score", 0.0)),
        dimension_scores=dict(data.get("dimension_scores", {})),
        evidence=[_evidence(item) for item in data.get("evidence", [])],
        missing_points=list(data.get("missing_points", [])),
        strengths=list(data.get("strengths", [])),
        confidence=data.get("confidence", 1.0),
    )
    _copy_base(artifact, data)
    return artifact


def _follow_up(data: dict[str, Any]) -> FollowUpDecisionArtifact:
    artifact = FollowUpDecisionArtifact(
        owner=data.get("owner", "FollowUpAgent"),
        question_id=data.get("question_id", ""),
        need_follow_up=data.get("need_follow_up", False),
        confidence=data.get("confidence", 1.0),
        target=data.get("target"),
        reason=data.get("reason"),
        missing_evidence=list(data.get("missing_evidence", [])),
    )
    artifact.normalized_target = data.get("normalized_target", artifact.normalized_target)
    _copy_base(artifact, data)
    return artifact


def _report(data: Optional[dict[str, Any]]) -> Optional[InterviewReportArtifact]:
    if not data:
        return None
    artifact = InterviewReportArtifact(
        owner=data.get("owner", "ReportAgent"),
        overall_score=data.get("overall_score", 0.0),
        dimension_scores=dict(data.get("dimension_scores", {})),
        verified_skills=list(data.get("verified_skills", [])),
        weak_skills=list(data.get("weak_skills", [])),
        evidence=[_evidence(item) for item in data.get("evidence", [])],
        role_match=data.get("role_match", ""),
        insufficient_evidence_areas=list(data.get("insufficient_evidence_areas", [])),
        interview_summary=data.get("interview_summary", ""),
        hiring_recommendation=data.get("hiring_recommendation", ""),
        improvement_suggestions=list(data.get("improvement_suggestions", [])),
    )
    _copy_base(artifact, data)
    return artifact


def _evidence(data: dict[str, Any]) -> Evidence:
    return Evidence(
        dimension=data.get("dimension", ""),
        claim=data.get("claim", ""),
        source_answer_id=data.get("source_answer_id", ""),
        quote_or_summary=data.get("quote_or_summary", data.get("answer_excerpt", "")),
        confidence=data.get("confidence", 0.0),
        evidence_id=data.get("evidence_id", ""),
        skill=data.get("skill"),
        source_question_id=data.get("source_question_id", ""),
        answer_excerpt=data.get("answer_excerpt", data.get("quote_or_summary", "")),
        evidence_type=data.get("evidence_type", "positive"),
        polarity=data.get("polarity", data.get("evidence_type", "positive")),
    )


def _capability(data: dict[str, Any]) -> CapabilityProfile:
    return CapabilityProfile(
        verified_skills=list(data.get("verified_skills", [])),
        weak_skills=list(data.get("weak_skills", [])),
        uncertain_skills=list(data.get("uncertain_skills", [])),
        dimension_scores=dict(data.get("dimension_scores", {})),
        dimension_coverage=dict(data.get("dimension_coverage", {})),
        evidence_count=dict(data.get("evidence_count", {})),
    )


def _runtime_metadata(data: dict[str, Any]) -> RuntimeMetadata:
    metadata = RuntimeMetadata(
        runtime_version=data.get("runtime_version", "0.2.0"),
        trace_id=data.get("trace_id", ""),
        errors=list(data.get("errors", [])),
        max_follow_up_round_per_question=data.get("max_follow_up_round_per_question", 2),
        session_timeout_seconds=data.get("session_timeout_seconds", 1800),
    )
    if data.get("started_at"):
        metadata.started_at = datetime.fromisoformat(data["started_at"])
    if data.get("updated_at"):
        metadata.updated_at = datetime.fromisoformat(data["updated_at"])
    return metadata


def _copy_base(artifact: Any, data: dict[str, Any]) -> None:
    artifact.id = data.get("id", artifact.id)
    if data.get("created_at"):
        artifact.created_at = datetime.fromisoformat(data["created_at"])
    artifact.metadata = dict(data.get("metadata", {}))


def _to_json(value: Any) -> Any:
    if is_dataclass(value):
        return _to_json(asdict(value))
    if isinstance(value, dict):
        return {str(k): _to_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_json(v) for v in value]
    if hasattr(value, "value"):
        return value.value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value
