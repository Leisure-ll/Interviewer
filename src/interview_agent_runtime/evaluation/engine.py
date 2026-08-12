from __future__ import annotations

from dataclasses import dataclass

from interview_agent_runtime.artifacts import Evidence, EvaluationArtifact
from interview_agent_runtime.blackboard import InterviewBlackboard


@dataclass
class EvidenceDrivenEvaluator:
    def evaluate(self, context: InterviewBlackboard) -> EvaluationArtifact:
        answer = context.latest_answer
        question = context.current_question
        if answer is None or question is None:
            raise RuntimeError("Cannot evaluate without answer and question")

        text = answer.normalized_text
        lower_text = text.lower()
        positives = self._positive_claims(question.dimension, lower_text)
        missing = self._missing_points(question.dimension, lower_text, len(text))
        score = self._score(positives, missing, len(text), question.is_follow_up)
        evidence = [
            Evidence(
                dimension=question.dimension,
                claim=claim,
                source_answer_id=answer.answer_id,
                source_question_id=question.question_id,
                quote_or_summary=text[:160],
                answer_excerpt=text[:160],
                confidence=0.82 if score >= 70 else 0.65,
                evidence_type="positive",
            )
            for claim in positives
        ]
        if not evidence:
            evidence.append(
                Evidence(
                    dimension=question.dimension,
                    claim="回答过短或缺少可验证细节",
                    source_answer_id=answer.answer_id,
                    source_question_id=question.question_id,
                    quote_or_summary=text[:160],
                    answer_excerpt=text[:160],
                    confidence=0.55,
                    evidence_type="insufficient",
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
            confidence=0.84 if text else 0.3,
            need_follow_up=bool(missing) and (
                not question.is_follow_up
                or context.current_question_follow_up_round()
                < context.runtime_metadata.max_follow_up_round_per_question
            ),
            follow_up_target=missing[0] if missing else None,
        )

    def _positive_claims(self, dimension: str, text: str) -> list[str]:
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
        if len(text) > 80:
            claims.append("回答包含一定实现细节")
        return claims

    def _missing_points(self, dimension: str, text: str, length: int) -> list[str]:
        missing = []
        if length < 40:
            missing.append("具体实现细节")
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
        return missing[:2]

    def _score(self, positives: list[str], missing: list[str], length: int, is_follow_up: bool) -> float:
        score = 55.0 + min(25.0, len(positives) * 6.0) + min(10.0, length / 20.0)
        score -= len(missing) * (8.0 if not is_follow_up else 5.0)
        return max(20.0, min(95.0, round(score, 1)))
