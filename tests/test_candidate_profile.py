from __future__ import annotations

from interview_agent_runtime.domain import CandidateProfile


def test_candidate_profile_keeps_skills_experience_and_gaps():
    profile = CandidateProfile(
        candidate_id="c1",
        target_role="Java Backend",
        years_of_experience=2.5,
        skills=["Java", "Redis"],
        potential_gaps=["System Design"],
        resume_keywords=["秒杀", "缓存"],
    )

    assert profile.years_of_experience == 2.5
    assert "Redis" in profile.skills
    assert profile.potential_gaps == ["System Design"]
