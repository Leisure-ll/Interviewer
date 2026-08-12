from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from interview_agent_runtime.artifacts import Evidence, EvaluationArtifact
from interview_agent_runtime.context import EvaluationAgentContext
from interview_agent_runtime.evaluation.score_policy import ScorePolicy


@dataclass
class EvidenceDrivenEvaluator:
    score_policy: ScorePolicy = field(default_factory=ScorePolicy)

    def evaluate(self, context: EvaluationAgentContext, draft: Optional[dict[str, Any]] = None) -> EvaluationArtifact:
        answer = context.current_answer
        question = context.current_question
        if answer is None or question is None:
            raise RuntimeError("Cannot evaluate without answer and question")

        text = answer.normalized_text
        lower_text = text.lower()
        positives = self._draft_list(draft, "matched_points") or self._draft_list(draft, "strengths")
        if not positives:
            positives = self._positive_claims(question.dimension, lower_text, question.expected_points)
        missing = self._draft_list(draft, "missing_points")
        if not missing:
            missing = self._missing_points(question.dimension, lower_text, len(text), question.expected_points)
        score = self.score_policy.score(
            matched_points=positives,
            missing_points=missing,
            answer_length=len(text),
            is_follow_up=question.is_follow_up,
        )
        evidence = self._evidence_from_draft(draft, context)
        if not evidence:
            evidence = [
                Evidence(
                    dimension=question.dimension,
                    skill=self._claim_skill(claim, question.related_skills),
                    claim=claim,
                    source_answer_id=answer.answer_id,
                    source_question_id=question.question_id,
                    quote_or_summary=text[:160],
                    answer_excerpt=text[:160],
                    confidence=0.82 if score >= 70 else 0.65,
                    evidence_type="positive",
                    polarity="positive",
                )
                for claim in positives
            ]
        if not evidence:
            evidence.append(
                Evidence(
                    dimension=question.dimension,
                    skill=question.related_skills[0] if question.related_skills else None,
                    claim="回答过短或缺少可验证细节",
                    source_answer_id=answer.answer_id,
                    source_question_id=question.question_id,
                    quote_or_summary=text[:160],
                    answer_excerpt=text[:160],
                    confidence=0.55,
                    evidence_type="insufficient",
                    polarity="uncertain",
                )
            )
        return EvaluationArtifact(
            owner="EvaluatorAgent",
            question_id=question.question_id,
            answer_id=answer.answer_id,
            score=score,
            dimension_scores={question.dimension: score},
            evidence=evidence,
            strengths=positives,
            missing_points=missing,
            confidence=self._draft_confidence(draft, 0.84 if text else 0.3),
        )

    def _draft_list(self, draft: Optional[dict[str, Any]], key: str) -> list[str]:
        if not draft:
            return []
        value = draft.get(key)
        if not isinstance(value, list):
            return []
        return [str(item) for item in value if str(item).strip()]

    def _draft_confidence(self, draft: Optional[dict[str, Any]], fallback: float) -> float:
        if not draft:
            return fallback
        value = draft.get("confidence")
        if isinstance(value, (int, float)):
            return max(0.0, min(1.0, float(value)))
        return fallback

    def _evidence_from_draft(self, draft: Optional[dict[str, Any]], context: EvaluationAgentContext) -> list[Evidence]:
        if not draft or not isinstance(draft.get("evidence"), list):
            return []
        answer = context.current_answer
        question = context.current_question
        if answer is None or question is None:
            return []
        evidence = []
        for item in draft["evidence"]:
            if not isinstance(item, dict):
                continue
            claim = str(item.get("claim", "")).strip()
            if not claim:
                continue
            confidence = item.get("confidence", 0.78)
            if not isinstance(confidence, (int, float)):
                confidence = 0.78
            polarity = str(item.get("polarity", "positive"))
            evidence.append(
                Evidence(
                    dimension=str(item.get("dimension") or question.dimension),
                    skill=item.get("skill") or self._claim_skill(claim, question.related_skills),
                    claim=claim,
                    source_answer_id=answer.answer_id,
                    source_question_id=question.question_id,
                    quote_or_summary=str(item.get("answer_excerpt") or answer.normalized_text[:160]),
                    answer_excerpt=str(item.get("answer_excerpt") or answer.normalized_text[:160]),
                    confidence=max(0.0, min(1.0, float(confidence))),
                    evidence_type="positive" if polarity == "positive" else "insufficient",
                    polarity=polarity if polarity in {"positive", "negative", "uncertain"} else "uncertain",
                )
            )
        return evidence

    def _positive_claims(self, dimension: str, text: str, expected_points: list[str]) -> list[str]:
        rules = {
            "Java Backend": [
                ("cache aside", "理解 Cache Aside 缓存模式"),
                ("缓存", "能围绕缓存场景作答"),
                ("消息队列", "提到了异步补偿机制"),
                ("重试", "考虑了失败重试"),
                ("监控", "考虑了可观测和告警"),
                ("事务", "关注事务一致性"),
            ],
            "Agent Engineering": [
                ("状态机", "能用状态机控制流程"),
                ("artifact", "理解结构化 Artifact 协作"),
                ("blackboard", "理解 Blackboard 共享状态"),
                ("工具", "考虑工具调用治理"),
                ("checkpoint", "考虑中断恢复"),
                ("fallback", "考虑模型失败兜底"),
            ],
            "System Design": [
                ("限流", "考虑流量保护"),
                ("降级", "考虑服务降级"),
                ("一致性", "关注一致性权衡"),
                ("异步", "考虑异步解耦"),
            ],
        }
        claims = [claim for keyword, claim in rules.get(dimension, []) if keyword in text]
        for point in expected_points:
            if point and _point_matched(point, text):
                claims.append(f"覆盖预期要点：{point}")
        if len(text) > 80:
            claims.append("回答包含一定实现细节")
        return _dedupe(claims)

    def _missing_points(self, dimension: str, text: str, length: int, expected_points: list[str]) -> list[str]:
        missing = []
        if length < 40:
            missing.append("具体实现细节")
        for point in expected_points:
            if point and not _point_matched(point, text):
                missing.append(point)
        if dimension == "Java Backend":
            if "失败" not in text and "重试" not in text and "补偿" not in text:
                missing.append("失败补偿策略")
            if "监控" not in text and "告警" not in text:
                missing.append("监控告警")
        if dimension == "Agent Engineering":
            if "状态" not in text:
                missing.append("状态控制")
            if "工具" not in text and "权限" not in text:
                missing.append("工具权限控制")
            if "checkpoint" not in text.lower() and "恢复" not in text:
                missing.append("中断恢复")
        return _dedupe(missing)[:3]

    def _claim_skill(self, claim: str, related_skills: list[str]) -> Optional[str]:
        for skill in related_skills:
            if skill.lower() in claim.lower():
                return skill
        return related_skills[0] if related_skills else None


def _dedupe(items: list[str]) -> list[str]:
    result = []
    for item in items:
        if item not in result:
            result.append(item)
    return result


def _point_matched(point: str, text: str) -> bool:
    point_text = point.lower().strip()
    if point_text in text:
        return True
    aliases = {
        "工具权限": ["权限控制", "工具调用"],
        "工具权限控制": ["权限控制", "工具调用"],
        "状态恢复": ["恢复", "checkpoint", "持久化"],
        "异常处理": ["失败", "异常", "重试", "补偿"],
        "具体做法": ["方案", "实现", "通过"],
        "结果": ["结果", "验证", "监控"],
    }
    return any(alias.lower() in text for alias in aliases.get(point, []))
