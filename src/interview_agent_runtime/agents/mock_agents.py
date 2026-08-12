from __future__ import annotations

from interview_agent_runtime.agents.base import BaseInterviewAgent
from interview_agent_runtime.artifacts import (
    AgentArtifact,
    CandidateProfileArtifact,
    EvaluationArtifact,
    Evidence,
    FollowUpDecisionArtifact,
    InterviewPlanArtifact,
    InterviewReportArtifact,
    QuestionArtifact,
)
from interview_agent_runtime.blackboard import InterviewBlackboard
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
        return CandidateProfileArtifact(owner=self.name, resume_id=resume.get("resume_id", ""), skills=resume.get("skills", []))


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
        dimensions = [
            {
                "name": "Java Backend",
                "weight": 0.5,
                "difficulty": "medium",
                "question_budget": 1,
                "follow_up_budget": 1,
                "coverage_target": 0.7,
            },
            {
                "name": "Agent Engineering",
                "weight": 0.5,
                "difficulty": "medium",
                "question_budget": 1,
                "follow_up_budget": 0,
                "coverage_target": 0.7,
            },
        ]
        return InterviewPlanArtifact(owner=self.name, dimensions=dimensions, total_question_budget=2, total_follow_up_budget=1)


class QuestionAgent(BaseInterviewAgent):
    name = "QuestionAgent"
    stages = {InterviewStage.QUESTION_PREPARING, InterviewStage.NEXT_QUESTION, InterviewStage.FOLLOW_UP}

    def required_skill(self, context: InterviewBlackboard) -> str:
        return "question-generation"

    async def execute(
        self,
        context: InterviewBlackboard,
        skill: SkillDefinition,
        tools: ToolExecutor,
        visible_tools: set[str],
    ) -> AgentArtifact:
        if context.current_stage == InterviewStage.FOLLOW_UP:
            decision = context.latest_follow_up_decision
            question = context.current_question
            target = decision.target if decision else "关键细节"
            return QuestionArtifact(
                owner=self.name,
                question_id=f"{question.question_id}:fu1" if question else "follow-up-1",
                title=f"你刚才提到的 {target} 可以展开说一下具体处理方案吗？",
                dimension=question.dimension if question else context.current_dimension,
                difficulty=question.difficulty if question else "medium",
                reference_answer=question.reference_answer if question else "",
                source="follow_up",
                is_follow_up=True,
            )

        tool_context = ToolContext(context.session_id, self.name, skill.name, context)
        bank = await tools.call("question_bank.search", {"limit": 3}, tool_context, visible_tools)
        candidates = bank.get("questions", [])
        for item in candidates:
            if item["question_id"] not in context.asked_question_ids:
                context.question_budget -= 1
                return QuestionArtifact(
                    owner=self.name,
                    question_id=item["question_id"],
                    title=item["title"],
                    dimension=item["dimension"],
                    difficulty=item.get("difficulty", "medium"),
                    reference_answer=item.get("reference_answer", ""),
                    source="qdrant_fallback",
                )
        raise RuntimeError("No available question candidates")


class EvaluatorAgent(BaseInterviewAgent):
    name = "EvaluatorAgent"
    stages = {InterviewStage.EVALUATING}

    def required_skill(self, context: InterviewBlackboard) -> str:
        return "evaluate-answer"

    async def execute(
        self,
        context: InterviewBlackboard,
        skill: SkillDefinition,
        tools: ToolExecutor,
        visible_tools: set[str],
    ) -> AgentArtifact:
        answer = context.latest_answer
        question = context.current_question
        if answer is None or question is None:
            raise RuntimeError("Cannot evaluate without answer and question")
        missing = []
        score = 82.0
        if len(answer.text.strip()) < 30:
            score = 58.0
            missing.append("缺少关键细节")
        evidence = [
            Evidence(
                dimension=question.dimension,
                claim="候选人回答覆盖了部分考察点",
                source_answer_id=answer.answer_id,
                quote_or_summary=answer.text[:120],
                confidence=0.78,
            )
        ]
        return EvaluationArtifact(
            owner=self.name,
            question_id=question.question_id,
            answer_id=answer.answer_id,
            score=score,
            dimension_scores={question.dimension: score},
            evidence=evidence,
            missing_points=missing,
            confidence=0.82,
            need_follow_up=bool(missing),
            follow_up_target=missing[0] if missing else None,
        )


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
        target = evaluation.follow_up_target or ""
        return FollowUpDecisionArtifact(
            owner=self.name,
            question_id=question.question_id,
            need_follow_up=evaluation.need_follow_up,
            confidence=0.87 if evaluation.need_follow_up else 0.75,
            target=target,
            reason="当前回答证据不足，需要补充关键处理细节" if evaluation.need_follow_up else "回答已覆盖主要证据",
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
        scores = context.dimension_scores
        overall = sum(scores.values()) / max(1, len(scores))
        weak = [dim for dim, score in scores.items() if score < 70]
        verified = [dim for dim, score in scores.items() if score >= 70]
        return InterviewReportArtifact(
            owner=self.name,
            overall_score=overall,
            dimension_scores=dict(scores),
            verified_skills=verified,
            weak_skills=weak,
            evidence=list(context.evidence),
        )


