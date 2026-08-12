from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from interview_agent_runtime.artifacts import QuestionArtifact, artifact_id
from interview_agent_runtime.blackboard import InterviewBlackboard
from interview_agent_runtime.context import QuestionAgentContext
from interview_agent_runtime.domain import InterviewDimension
from interview_agent_runtime.skills import SkillDefinition
from interview_agent_runtime.tools import ToolContext, ToolExecutor


@dataclass
class QuestionValidationResult:
    accepted: bool
    reasons: list[str] = field(default_factory=list)


class QuestionGenerationPipeline:
    async def generate(
        self,
        context: InterviewBlackboard,
        agent_context: QuestionAgentContext,
        skill: SkillDefinition,
        tools: ToolExecutor,
        visible_tools: set[str],
        agent_name: str,
    ) -> QuestionArtifact:
        if context.current_stage.value == "FOLLOW_UP":
            return self._build_follow_up(context, agent_context, agent_name)

        dimension = self._select_dimension(context, agent_context)
        candidates = await self._retrieve_candidates(context, skill, tools, visible_tools, agent_name, dimension)
        for item in candidates:
            question = self._candidate_to_artifact(item, dimension, agent_name)
            result = self.validate(question, context)
            if result.accepted:
                return question

        return self._fallback_question(context, dimension, agent_name)

    async def _retrieve_candidates(
        self,
        context: InterviewBlackboard,
        skill: SkillDefinition,
        tools: ToolExecutor,
        visible_tools: set[str],
        agent_name: str,
        dimension: InterviewDimension,
    ) -> list[dict[str, Any]]:
        tool_context = ToolContext(context.session_id, agent_name, skill.name, context)
        bank = await tools.call(
            "question_bank.search",
            {
                "limit": 5,
                "dimension": dimension.name,
                "difficulty": dimension.difficulty,
                "skills": context.candidate.skills if context.candidate else [],
            },
            tool_context,
            visible_tools,
        )
        return bank.get("questions", [])

    def validate(self, question: QuestionArtifact, context: InterviewBlackboard) -> QuestionValidationResult:
        reasons = []
        if not question.title.strip():
            reasons.append("empty_title")
        if len(question.title.strip()) < 8:
            reasons.append("too_short")
        if question.question_id in context.asked_question_ids:
            reasons.append("duplicate_id")
        if self._similar_to_history(question, context):
            reasons.append("duplicate_semantic")
        expected_dimension = context.current_dimension
        if context.plan is not None:
            selected = context.plan.next_dimension(context.dimension_coverage)
            if selected is not None:
                expected_dimension = selected.name
        if expected_dimension and question.dimension != expected_dimension:
            reasons.append("dimension_mismatch")
        if any(word in question.title.lower() for word in ["年龄", "婚育", "宗教"]):
            reasons.append("sensitive")
        if context.position_profile:
            keywords = set(context.position_profile.keywords + context.position_profile.required_skills + context.position_profile.preferred_skills)
            related = set(question.related_skills + question.tags + [question.dimension])
            if keywords and not (keywords & related) and question.dimension not in context.position_profile.competency_dimensions:
                reasons.append("job_irrelevant")
        return QuestionValidationResult(not reasons, reasons)

    def _similar_to_history(self, question: QuestionArtifact, context: InterviewBlackboard) -> bool:
        fingerprint = _fingerprint(question.title)
        for item in context.question_history[-5:]:
            previous = _fingerprint(item.title)
            if not previous:
                continue
            overlap = len(fingerprint & previous) / max(1, min(len(fingerprint), len(previous)))
            if overlap >= 0.75:
                return True
        return False

    def _select_dimension(self, context: InterviewBlackboard, agent_context: QuestionAgentContext) -> InterviewDimension:
        if agent_context.current_plan is None:
            raise RuntimeError("Cannot generate question without interview plan")
        dimension = agent_context.current_plan.next_dimension(agent_context.capability_profile.dimension_coverage)
        if dimension is None:
            raise RuntimeError("No remaining interview dimension")
        context.current_dimension = dimension.name
        return dimension

    def _candidate_to_artifact(self, item: dict[str, Any], dimension: InterviewDimension, agent_name: str) -> QuestionArtifact:
        return QuestionArtifact(
            owner=agent_name,
            question_id=item.get("question_id") or artifact_id("question"),
            title=item.get("title", ""),
            dimension=item.get("dimension") or dimension.name,
            difficulty=item.get("difficulty") or dimension.difficulty,
            reference_answer=item.get("reference_answer", ""),
            source=item.get("source", "question_bank"),
            target_evidence=item.get("target_evidence", []),
            expected_points=item.get("expected_points", item.get("target_evidence", [])),
            related_skills=item.get("related_skills", []),
            tags=item.get("tags", []),
        )

    def _fallback_question(self, context: InterviewBlackboard, dimension: InterviewDimension, agent_name: str) -> QuestionArtifact:
        skill_hint = ""
        if context.candidate and context.candidate.skills:
            skill_hint = f"，结合候选人简历中的 {context.candidate.skills[0]}"
        return QuestionArtifact(
            owner=agent_name,
            question_id=artifact_id(f"fallback_{dimension.name.replace(' ', '_').lower()}"),
            title=f"请围绕 {dimension.name}{skill_hint}，说明一个你实际处理过的问题、方案和结果。",
            dimension=dimension.name,
            difficulty=dimension.difficulty,
            reference_answer="需要包含场景、约束、方案、权衡、结果和复盘。",
            source="runtime_fallback",
            target_evidence=["场景", "方案", "权衡", "结果"],
            expected_points=["场景", "约束", "方案", "权衡", "结果"],
            related_skills=[dimension.name],
        )

    def _build_follow_up(
        self,
        context: InterviewBlackboard,
        agent_context: QuestionAgentContext,
        agent_name: str,
    ) -> QuestionArtifact:
        decision = context.latest_follow_up_decision
        question = context.current_question
        target = decision.target if decision and decision.target else "关键细节"
        parent_id = question.parent_question_id or question.question_id if question else "follow-up"
        round_no = context.question_follow_up_rounds.get(parent_id, 0) + 1
        return QuestionArtifact(
            owner=agent_name,
            question_id=f"{parent_id}:fu{round_no}",
            title=f"刚才关于「{target}」的信息还不够，请补充你的具体做法、异常处理和结果。",
            dimension=question.dimension if question else context.current_dimension,
            difficulty=question.difficulty if question else "medium",
            reference_answer=question.reference_answer if question else "",
            source="follow_up",
            is_follow_up=True,
            target_evidence=[target],
            expected_points=[target, "具体做法", "异常处理", "结果"],
            related_skills=question.related_skills if question else [],
            parent_question_id=parent_id,
        )


def _fingerprint(text: str) -> set[str]:
    normalized = "".join(ch.lower() for ch in text if ch.isalnum())
    terms = set()
    for keyword in [
        "redis",
        "缓存",
        "一致性",
        "消息队列",
        "agent",
        "状态机",
        "工具",
        "checkpoint",
        "恢复",
        "限流",
        "降级",
    ]:
        if keyword in normalized:
            terms.add(keyword)
    if not terms:
        terms = {normalized[i : i + 2] for i in range(max(0, len(normalized) - 1))}
    return terms
