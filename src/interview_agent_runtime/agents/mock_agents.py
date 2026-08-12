from __future__ import annotations

from typing import Any, Optional

from interview_agent_runtime.agents.base import BaseInterviewAgent
from interview_agent_runtime.artifacts import (
    AgentArtifact,
    CandidateProfileArtifact,
    FollowUpDecisionArtifact,
    InterviewPlanArtifact,
    InterviewReportArtifact,
)
from interview_agent_runtime.blackboard import InterviewBlackboard
from interview_agent_runtime.context import (
    AgentContext,
    EvaluationAgentContext,
    FollowUpAgentContext,
    PlannerAgentContext,
    ProfileAgentContext,
    QuestionAgentContext,
    ReportAgentContext,
)
from interview_agent_runtime.domain import (
    CandidateProfile,
    InterviewDimension,
    InterviewPlan,
    InterviewStage,
    PositionProfile,
)
from interview_agent_runtime.evaluation import EvidenceDrivenEvaluator
from interview_agent_runtime.prompting import PromptAssembler
from interview_agent_runtime.providers import LLMProvider
from interview_agent_runtime.questioning import QuestionGenerationPipeline
from interview_agent_runtime.skills import SkillDefinition
from interview_agent_runtime.tools import ToolContext, ToolExecutor


class ProfileAgent(BaseInterviewAgent):
    name = "ProfileAgent"
    stages = {InterviewStage.PROFILE_ANALYSIS}
    draft_schema = "ProfileDraft"

    def __init__(self, llm_provider: Optional[LLMProvider] = None, prompt_assembler: Optional[PromptAssembler] = None):
        self.llm_provider = llm_provider
        self.prompt_assembler = prompt_assembler or PromptAssembler()

    def required_skill(self, context: InterviewBlackboard) -> str:
        return "profile-analysis"

    async def execute(
        self,
        context: InterviewBlackboard,
        agent_context: AgentContext,
        skill: SkillDefinition,
        tools: ToolExecutor,
        visible_tools: set[str],
    ) -> AgentArtifact:
        assert isinstance(agent_context, ProfileAgentContext)
        tool_context = ToolContext(context.session_id, self.name, skill.name, context)
        resume = await tools.call("resume.retrieve", {}, tool_context, visible_tools)
        jd = await tools.call("jd.retrieve", {}, tool_context, visible_tools)
        draft = await self._profile_draft(agent_context, skill)
        candidate_data = draft.get("candidate_profile", {}) if isinstance(draft.get("candidate_profile"), dict) else {}
        position_data = draft.get("position_profile", {}) if isinstance(draft.get("position_profile"), dict) else {}
        candidate = CandidateProfile(
            candidate_id=resume.get("candidate_id", context.session_id),
            target_role=candidate_data.get("target_role") or jd.get("position"),
            years_of_experience=candidate_data.get("years_of_experience", resume.get("years_of_experience")),
            skills=_list(candidate_data.get("skills")) or list(resume.get("skills", [])),
            project_experiences=list(resume.get("project_experiences", [])),
            strengths=_list(candidate_data.get("strengths")) or list(resume.get("strengths", [])),
            possible_weaknesses=_list(candidate_data.get("possible_weaknesses")) or list(resume.get("possible_weaknesses", [])),
            potential_gaps=_list(candidate_data.get("potential_gaps")) or list(resume.get("potential_gaps", resume.get("possible_weaknesses", []))),
            resume_keywords=_list(candidate_data.get("resume_keywords")) or list(resume.get("resume_keywords", resume.get("skills", []))),
        )
        position = PositionProfile(
            role_name=position_data.get("role_name") or jd.get("position", "Software Engineer"),
            required_skills=_list(position_data.get("required_skills")) or list(jd.get("required_skills", [])),
            preferred_skills=_list(position_data.get("preferred_skills")) or list(jd.get("preferred_skills", [])),
            responsibilities=_list(position_data.get("responsibilities")) or list(jd.get("responsibilities", [])),
            competency_dimensions=_list(position_data.get("competency_dimensions")) or list(jd.get("dimensions", [])),
            seniority=position_data.get("seniority") or jd.get("seniority"),
            keywords=_list(position_data.get("keywords")) or list(jd.get("keywords", jd.get("required_skills", []))),
        )
        return CandidateProfileArtifact(
            owner=self.name,
            candidate_profile=candidate,
            position_profile=position,
            resume_id=resume.get("resume_id", ""),
            confidence=0.9,
        )

    async def _profile_draft(self, agent_context: ProfileAgentContext, skill: SkillDefinition) -> dict[str, Any]:
        if self.llm_provider is None:
            return {}
        try:
            messages = self.prompt_assembler.assemble(
                skill=skill,
                context=agent_context,
                output_schema=self.draft_schema,
            )
            response = await self.llm_provider.structured_generate(
                messages=messages,
                output_schema=self.draft_schema,
                timeout=skill.timeout,
            )
            return response.parsed
        except Exception:
            return {}


class PlannerAgent(BaseInterviewAgent):
    name = "PlannerAgent"
    stages = {InterviewStage.INTERVIEW_PLANNING}

    def required_skill(self, context: InterviewBlackboard) -> str:
        return "interview-planning"

    async def execute(
        self,
        context: InterviewBlackboard,
        agent_context: AgentContext,
        skill: SkillDefinition,
        tools: ToolExecutor,
        visible_tools: set[str],
    ) -> AgentArtifact:
        assert isinstance(agent_context, PlannerAgentContext)
        tool_context = ToolContext(context.session_id, self.name, skill.name, context)
        rubric = await tools.call("rubric.retrieve", {}, tool_context, visible_tools)
        position = agent_context.position_profile
        candidate = agent_context.candidate_profile
        dimension_names = list(position.competency_dimensions if position else ["Java Backend", "Agent Engineering"])
        if candidate:
            skills = set(candidate.skills + candidate.resume_keywords)
            if {"Redis", "Kafka", "MySQL"} & skills and "Project Experience" not in dimension_names:
                dimension_names.append("Project Experience")
            if "System Design" not in dimension_names and {"高并发", "秒杀", "System Design"} & skills:
                dimension_names.append("System Design")
        required = set(position.required_skills if position else [])
        preferred = set(position.preferred_skills if position else [])
        candidate_skills = set(candidate.skills if candidate else [])
        weights = self._dimension_weights(dimension_names, required, preferred, candidate_skills)
        dimensions = []
        for name in dimension_names:
            is_core = name in required or name.lower() in {"java backend", "java core", "project experience"}
            is_claimed = name in candidate_skills or any(skill.lower() in name.lower() for skill in candidate_skills)
            dimensions.append(
                InterviewDimension(
                    name=name,
                    weight=weights[name],
                    target_level="production" if is_core or is_claimed else "working",
                    question_budget=2 if is_core or is_claimed else 1,
                    follow_up_budget=1 if is_core or is_claimed else 0,
                    coverage_target=0.65,
                    difficulty="hard" if is_core else "medium",
                )
            )
        total_questions = sum(item.question_budget for item in dimensions)
        total_follow_ups = sum(item.follow_up_budget for item in dimensions)
        plan = InterviewPlan(
            dimensions=dimensions,
            total_question_budget=total_questions,
            total_follow_up_budget=total_follow_ups,
            estimated_duration_minutes=max(8, total_questions * 4 + total_follow_ups * 2),
        )
        return InterviewPlanArtifact(
            owner=self.name,
            plan=plan,
            confidence=0.88 if rubric.get("rubric") else 0.75,
        )

    def _dimension_weights(
        self,
        dimension_names: list[str],
        required: set[str],
        preferred: set[str],
        candidate_skills: set[str],
    ) -> dict[str, float]:
        raw: dict[str, float] = {}
        for name in dimension_names:
            score = 1.0
            if name in required:
                score += 1.2
            if name in preferred:
                score += 0.6
            if any(skill.lower() in name.lower() for skill in candidate_skills):
                score += 0.5
            if name == "Project Experience":
                score += 0.4
            raw[name] = score
        total = sum(raw.values()) or 1.0
        return {name: round(value / total, 2) for name, value in raw.items()}


class QuestionAgent(BaseInterviewAgent):
    name = "QuestionAgent"
    stages = {
        InterviewStage.QUESTION_PREPARING,
        InterviewStage.NEXT_QUESTION,
        InterviewStage.NEXT_DIMENSION,
        InterviewStage.FOLLOW_UP,
    }

    def __init__(self, pipeline: Optional[QuestionGenerationPipeline] = None):
        self.pipeline = pipeline or QuestionGenerationPipeline()

    def required_skill(self, context: InterviewBlackboard) -> str:
        return "question-generation"

    async def execute(
        self,
        context: InterviewBlackboard,
        agent_context: AgentContext,
        skill: SkillDefinition,
        tools: ToolExecutor,
        visible_tools: set[str],
    ) -> AgentArtifact:
        assert isinstance(agent_context, QuestionAgentContext)
        return await self.pipeline.generate(context, agent_context, skill, tools, visible_tools, self.name)


class EvaluatorAgent(BaseInterviewAgent):
    name = "EvaluatorAgent"
    stages = {InterviewStage.EVALUATING}
    draft_schema = "EvaluationDraft"

    def __init__(
        self,
        evaluator: Optional[EvidenceDrivenEvaluator] = None,
        llm_provider: Optional[LLMProvider] = None,
        prompt_assembler: Optional[PromptAssembler] = None,
    ):
        self.evaluator = evaluator or EvidenceDrivenEvaluator()
        self.llm_provider = llm_provider
        self.prompt_assembler = prompt_assembler or PromptAssembler()

    def required_skill(self, context: InterviewBlackboard) -> str:
        return "evaluate-answer"

    async def execute(
        self,
        context: InterviewBlackboard,
        agent_context: AgentContext,
        skill: SkillDefinition,
        tools: ToolExecutor,
        visible_tools: set[str],
    ) -> AgentArtifact:
        assert isinstance(agent_context, EvaluationAgentContext)
        draft = await self._evaluation_draft(agent_context, skill)
        return self.evaluator.evaluate(agent_context, draft=draft)

    async def _evaluation_draft(self, agent_context: EvaluationAgentContext, skill: SkillDefinition) -> dict[str, Any]:
        if self.llm_provider is None:
            return {}
        try:
            messages = self.prompt_assembler.assemble(
                skill=skill,
                context=agent_context,
                output_schema=self.draft_schema,
            )
            response = await self.llm_provider.structured_generate(
                messages=messages,
                output_schema=self.draft_schema,
                timeout=skill.timeout,
            )
            return response.parsed
        except Exception:
            return {}


class FollowUpAgent(BaseInterviewAgent):
    name = "FollowUpAgent"
    stages = {InterviewStage.DECISION}
    draft_schema = "FollowUpDraft"

    def __init__(self, llm_provider: Optional[LLMProvider] = None, prompt_assembler: Optional[PromptAssembler] = None):
        self.llm_provider = llm_provider
        self.prompt_assembler = prompt_assembler or PromptAssembler()

    def required_skill(self, context: InterviewBlackboard) -> str:
        return "follow-up-decision"

    async def execute(
        self,
        context: InterviewBlackboard,
        agent_context: AgentContext,
        skill: SkillDefinition,
        tools: ToolExecutor,
        visible_tools: set[str],
    ) -> AgentArtifact:
        assert isinstance(agent_context, FollowUpAgentContext)
        evaluation = agent_context.current_evaluation
        question = agent_context.current_question
        if evaluation is None or question is None:
            raise RuntimeError("Cannot decide follow-up without evaluation")
        draft = await self._follow_up_draft(agent_context, skill)
        target = self._select_target(agent_context, draft)
        need_follow_up = target is not None
        confidence = self._confidence(agent_context, bool(target), draft)
        return FollowUpDecisionArtifact(
            owner=self.name,
            question_id=question.question_id,
            need_follow_up=need_follow_up,
            confidence=confidence,
            target=target,
            reason=str(draft.get("reason") or self._reason(agent_context, target)),
            missing_evidence=_list(draft.get("missing_evidence")) or list(agent_context.missing_points),
        )

    async def _follow_up_draft(self, agent_context: FollowUpAgentContext, skill: SkillDefinition) -> dict[str, Any]:
        if self.llm_provider is None:
            return {}
        try:
            messages = self.prompt_assembler.assemble(
                skill=skill,
                context=agent_context,
                output_schema=self.draft_schema,
            )
            response = await self.llm_provider.structured_generate(
                messages=messages,
                output_schema=self.draft_schema,
                timeout=skill.timeout,
            )
            return response.parsed
        except Exception:
            return {}

    def _select_target(self, context: FollowUpAgentContext, draft: Optional[dict[str, Any]] = None) -> Optional[str]:
        if context.current_question and context.current_question.is_follow_up:
            return None
        if context.follow_up_budget <= 0 or context.dimension_follow_up_budget <= 0:
            return None
        if context.current_evaluation is None or context.current_evaluation.confidence < 0.45:
            return None
        if not context.missing_points:
            return None
        coverage = context.capability_summary.get("dimension_coverage", {})
        if isinstance(coverage, dict) and coverage.get(context.current_dimension, 0.0) >= 0.85:
            return None
        if draft and draft.get("need_follow_up") is False:
            return None
        if draft and str(draft.get("target", "")).strip():
            return str(draft["target"]).strip()
        return context.missing_points[0]

    def _confidence(self, context: FollowUpAgentContext, has_target: bool, draft: Optional[dict[str, Any]] = None) -> float:
        if draft and isinstance(draft.get("confidence"), (int, float)):
            return round(max(0.0, min(1.0, float(draft["confidence"]))), 2)
        if not has_target:
            return 0.72
        evidence_gap = min(0.2, len(context.missing_points) * 0.05)
        low_coverage_boost = 0.1
        coverage = context.capability_summary.get("dimension_coverage", {})
        if isinstance(coverage, dict) and coverage.get(context.current_dimension, 0.0) >= 0.6:
            low_coverage_boost = 0.0
        return round(min(0.95, 0.72 + evidence_gap + low_coverage_boost), 2)

    def _reason(self, context: FollowUpAgentContext, target: Optional[str]) -> str:
        if target is None:
            return "当前回答没有需要继续追问的高价值证据缺口"
        return f"当前回答仍缺少「{target}」相关证据，需要局部追问验证"


class ReportAgent(BaseInterviewAgent):
    name = "ReportAgent"
    stages = {InterviewStage.REPORTING}

    def required_skill(self, context: InterviewBlackboard) -> str:
        return "interview-report"

    async def execute(
        self,
        context: InterviewBlackboard,
        agent_context: AgentContext,
        skill: SkillDefinition,
        tools: ToolExecutor,
        visible_tools: set[str],
    ) -> AgentArtifact:
        assert isinstance(agent_context, ReportAgentContext)
        scores = dict(agent_context.dimension_scores)
        overall = round(sum(scores.values()) / max(1, len(scores)), 1)
        weak = list(agent_context.capability_profile.weak_skills)
        verified = list(agent_context.capability_profile.verified_skills)
        uncertain = list(agent_context.capability_profile.uncertain_skills)
        if overall >= 80:
            recommendation = "建议进入下一轮"
        elif overall >= 65:
            recommendation = "建议结合岗位优先级人工复核"
        else:
            recommendation = "当前证据不足以支持通过"
        role = context.position_profile.role_name if context.position_profile else ""
        role_match_score = round(
            overall * 0.7
            + min(100.0, len(verified) * 25.0) * 0.2
            + max(0.0, 100.0 - len(uncertain) * 12.0) * 0.1,
            1,
        )
        return InterviewReportArtifact(
            owner=self.name,
            overall_score=overall,
            dimension_scores=scores,
            verified_skills=verified,
            weak_skills=weak,
            evidence=list(context.evidence),
            role_match=f"{role}：基于 {len(verified)} 个已验证维度评估",
            role_match_score=role_match_score,
            insufficient_evidence_areas=uncertain,
            interview_summary=f"完成 {len(context.answers)} 次回答，提取 {len(context.evidence)} 条能力证据。",
            hiring_recommendation=recommendation,
            improvement_suggestions=[f"补充 {item} 的具体案例" for item in weak],
        )


def _list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]
