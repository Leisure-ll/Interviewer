from __future__ import annotations

import asyncio

from interview_agent_runtime.application import InterviewApplicationService
from interview_agent_runtime.runtime import InterviewStage


def test_application_service_starts_with_custom_resume_and_jd():
    asyncio.run(_case())


async def _case():
    service = InterviewApplicationService()
    status = await service.start_interview(
        candidate_id="custom-candidate",
        resume={
            "skills": ["Python", "RAG"],
            "resume_keywords": ["Python", "RAG"],
            "years_of_experience": 1.0,
        },
        jd={
            "position": "AI Agent Intern",
            "required_skills": ["Agent Engineering"],
            "preferred_skills": ["RAG"],
            "dimensions": ["Agent Engineering"],
            "keywords": ["Agent", "RAG"],
        },
        session_id="app-service",
    )

    assert status.stage == InterviewStage.LISTENING
    assert status.current_question is not None
    assert status.current_question.dimension == "Agent Engineering"
