from __future__ import annotations

from typing import Optional

from interview_agent_runtime.agents.base import BaseInterviewAgent
from interview_agent_runtime.artifacts import (
    AgentArtifact,
    CandidateProfileArtifact,
    FollowUpDecisionArtifact,
    InterviewPlanArtifact,
    InterviewReportArtifact,
)
from interview_agent_runtime.blackboard import InterviewBlackboard
from interview_agent_runtime.domain import (
    CandidateProfile,
    InterviewDimension,
    InterviewPlan,
    PositionProfile,
)
from interview_agent_runtime.evaluation import EvidenceDrivenEvaluator
from interview_agent_runtime.questioning import QuestionGenerationPipeline
from interview_agent_runtime.runtime.states import InterviewStage
from interview_agent_runtime.skills import SkillDefinition
from interview_agent_runtime.tools import ToolContext, ToolExecutor


class ProfileAgent(BaseInterviewAgent):
    name = "ProfileAgent"
    stages = {InterviewStage.PROFILE_ANALYSIS}

    def required_skill(self, context: InterviewBlackboard) -> str:
        return "profile-analysis"

    async def execute(
        self,
        context: InterviewBlackboard,
        skill: SkillDefinition,
        tools: ToolExecutor,
        visible_tools: set[str],
    ) -> AgentArtifact:
        tool_context = ToolContext(context.session_id, self.name, skill.name, context)
        resume = await tools.call("resume.retrieve", {}, tool_context, visible_tools)
        jd = await tools.call("jd.retrieve", {}, tool_context, visible_tools)
        candidate = CandidateProfile(
            candidate_id=resume.get("candidate_id", context.session_id),
            target_role=jd.get("position"),
            years_of_experience=resume.get("years_of_experience"),
            skills=list(resume.get("skills", [])),
            project_experiences=list(resume.get("project_experiences", [])),
            strengths=list(resume.get("strengths", [])),
            possible_weaknesses=list(resume.get("possible_weaknesses", [])),
            potential_gaps=list(resume.get("potential_gaps", resume.get("possible_weaknesses", []))),
            resume_keywords=list(resume.get("resume_keywords", resume.get("skills", []))),
        )
        position = PositionProfile(
            role_name=jd.get("position", "Software Engineer"),
            required_skills=list(jd.get("required_skills", [])),
            preferred_skills=list(jd.get("preferred_skills", [])),
            responsibilities=list(jd.get("responsibilities", [])),
            competency_dimensions=list(jd.get("dimensions", [])),
            seniority=jd.get("seniority"),
            keywords=list(jd.get("keywords", jd.get("required_skills", []))),
        )
        return CandidateProfileArtifact(
            owner=self.name,
            candidate_profile=candidate,
            position_profile=position,
            resume_id=resume.get("resume_id", ""),
            confidence=0.9,
        )


class PlannerAgent(BaseInterviewAgent):
    name = "PlannerAgent"
    stages = {InterviewStage.INTERVIEW_PLANNING}

    def required_skill(self, context: InterviewBlackboard) -> str:
        return "interview-planning"

    async def execute(
        self,
        context: InterviewBlackboard,
        skill: SkillDefinition,
        tools: ToolExecutor,
        visible_tools: set[str],
    ) -> AgentArtifact:
        tool_context = ToolContext(context.session_id, self.name, skill.name, context)
        rubric = await tools.call("rubric.retrieve", {}, tool_context, visible_tools)
        position = context.position_profile
        if position is None and context.candidate_profile is not None:
            position = context.candidate_profile.position_profile
        candidate = context.candidate
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
        skill: SkillDefinition,
        tools: ToolExecutor,
        visible_tools: set[str],
    ) -> AgentArtifact:
        return await self.pipeline.generate(context, skill, tools, visible_tools, self.name)


class EvaluatorAgent(BaseInterviewAgent):
    name = "EvaluatorAgent"
    stages = {InterviewStage.EVALUATING}

    def __init__(self, evaluator: Optional[EvidenceDrivenEvaluator] = None):
        self.evaluator = evaluator or EvidenceDrivenEvaluator()

    def required_skill(self, context: InterviewBlackboard) -> str:
        return "evaluate-answer"

    async def execute(
        self,
        context: InterviewBlackboard,
        skill: SkillDefinition,
        tools: ToolExecutor,
        visible_tools: set[str],
    ) -> AgentArtifact:
        return self.evaluator.evaluate(context)


class FollowUpAgent(BaseInterviewAgent):
    name = "FollowUpAgent"
    stages = {InterviewStage.DECISION}

    def required_skill(self, context: InterviewBlackboard) -> str:
        return "follow-up-decision"

    async def execute(
        self,
        context: InterviewBlackboard,
        skill: SkillDefinition,
        tools: ToolExecutor,
        visible_tools: set[str],
    ) -> AgentArtifact:
        evaluation = context.latest_evaluation
        question = context.current_question
        if evaluation is None or question is None:
            raise RuntimeError("Cannot decide follow-up without evaluation")
        need_follow_up = evaluation.need_follow_up
        target = evaluation.follow_up_target if need_follow_up else None
        return FollowUpDecisionArtifact(
            owner=self.name,
            question_id=question.question_id,
            need_follow_up=need_follow_up,
            confidence=0.87 if need_follow_up else 0.78,
            target=target,
            reason="当前回答缺少关键可验证证据" if need_follow_up else "当前回答已覆盖主要考察点",
            missing_evidence=evaluation.missing_points,
        )


class ReportAgent(BaseInterviewAgent):
    name = "ReportAgent"
    stages = {InterviewStage.REPORTING}

    def required_skill(self, context: InterviewBlackboard) -> str:
        return "interview-report"

    async def execute(
        self,
        context: InterviewBlackboard,
        skill: SkillDefinition,
        tools: ToolExecutor,
        visible_tools: set[str],
    ) -> AgentArtifact:
        scores = dict(context.capability_profile.dimension_scores)
        overall = round(sum(scores.values()) / max(1, len(scores)), 1)
        weak = list(context.capability_profile.weak_skills)
        verified = list(context.capability_profile.verified_skills)
        uncertain = list(context.capability_profile.uncertain_skills)
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
