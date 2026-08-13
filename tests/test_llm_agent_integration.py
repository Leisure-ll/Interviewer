from __future__ import annotations

import asyncio

from interview_agent_runtime.harness.bootstrap import build_agent_registry
from interview_agent_runtime.harness import HarnessConfig, InterviewHarness
from interview_agent_runtime.providers import FakeLLMProvider
from interview_agent_runtime.runtime import InterviewStage


def test_profile_agent_uses_structured_llm_profile_when_available():
    asyncio.run(_profile_case())


async def _profile_case():
    provider = FakeLLMProvider(
        responses=[
            {
                "candidate_profile": {
                    "target_role": "Senior Java Engineer",
                    "years_of_experience": 5,
                    "skills": ["Java", "Kafka"],
                    "strengths": ["distributed systems"],
                    "potential_gaps": ["Redis cluster"],
                    "resume_keywords": ["Kafka", "DDD"],
                },
                "position_profile": {
                    "role_name": "Backend Platform Engineer",
                    "required_skills": ["Java", "Kafka"],
                    "preferred_skills": ["Redis"],
                    "responsibilities": ["build platform services"],
                    "competency_dimensions": ["Java", "Kafka", "System Design"],
                    "seniority": "senior",
                    "keywords": ["platform"],
                },
            }
        ]
    )
    harness = InterviewHarness.from_config(HarnessConfig.mock())
    harness.llm_provider = provider
    harness.agent_registry = build_agent_registry(llm_provider=provider)
    runtime = harness.create_runtime("llm-profile")
    board = await runtime.start_session("llm-profile")
    await runtime.run_step(board.session_id)
    await runtime.run_step(board.session_id)
    board = await runtime.load_context(board.session_id)

    assert board.candidate is not None
    assert board.candidate.skills == ["Java", "Kafka"]
    assert board.position_profile is not None
    assert board.position_profile.role_name == "Backend Platform Engineer"
    assert provider.calls[0]["output_schema"] == "ProfileDraft"


def test_evaluator_agent_uses_structured_llm_evidence_draft():
    asyncio.run(_evaluation_case())


async def _evaluation_case():
    provider = FakeLLMProvider(
        responses=[
            {},
            {
                "matched_points": ["说明了幂等恢复"],
                "missing_points": ["降级策略"],
                "evidence": [
                    {
                        "claim": "候选人说明 checkpoint 恢复需要幂等",
                        "skill": "checkpoint",
                        "answer_excerpt": "checkpoint 恢复时保证幂等",
                        "confidence": 0.91,
                        "polarity": "positive",
                    }
                ],
                "confidence": 0.9,
            },
        ]
    )
    harness = InterviewHarness.from_config(HarnessConfig.mock())
    harness.llm_provider = provider
    harness.agent_registry = build_agent_registry(llm_provider=provider)
    runtime = harness.create_runtime("llm-evaluation")
    board = await runtime.start_session("llm-evaluation")
    board = await runtime.run_until_waiting_or_done(board.session_id)
    await runtime.receive_answer(board.session_id, "checkpoint 恢复时保证幂等。")
    board = await runtime.run_until_waiting_or_done(board.session_id)

    assert board.evaluations
    assert board.evaluations[-1].strengths == ["说明了幂等恢复"]
    assert board.evidence[-1].claim == "候选人说明 checkpoint 恢复需要幂等"
    assert "EvaluationDraft" in [item["output_schema"] for item in provider.calls]


def test_followup_agent_uses_structured_llm_decision_draft():
    asyncio.run(_followup_case())


async def _followup_case():
    provider = FakeLLMProvider(
        responses=[
            {},
            {},
            {
                "need_follow_up": True,
                "target": "删除缓存失败后的补偿机制",
                "reason": "LLM identified missing compensation evidence",
                "missing_evidence": ["补偿机制"],
                "confidence": 0.89,
            },
        ]
    )
    harness = InterviewHarness.from_config(HarnessConfig.mock())
    harness.llm_provider = provider
    harness.agent_registry = build_agent_registry(llm_provider=provider)
    runtime = harness.create_runtime("llm-followup")
    board = await runtime.start_session("llm-followup")
    board = await runtime.run_until_waiting_or_done(board.session_id)
    await runtime.receive_answer(board.session_id, "用缓存。")
    board = await runtime.run_until_waiting_or_done(board.session_id)

    assert board.current_stage == InterviewStage.LISTENING
    assert board.latest_follow_up_decision is not None
    assert board.latest_follow_up_decision.target == "删除缓存失败后的补偿机制"
    assert board.latest_follow_up_decision.reason == "LLM identified missing compensation evidence"
    assert provider.calls[-1]["output_schema"] == "FollowUpDraft"
