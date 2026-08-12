from __future__ import annotations

from interview_agent_runtime.domain import PositionProfile


def test_position_profile_keeps_required_skills_and_keywords():
    profile = PositionProfile(
        role_name="Agent Backend Intern",
        seniority="intern",
        required_skills=["Java Backend"],
        preferred_skills=["Redis"],
        competency_dimensions=["Java Backend", "System Design"],
        keywords=["Java", "高并发"],
    )

    assert profile.role_name == "Agent Backend Intern"
    assert "System Design" in profile.competency_dimensions
    assert "高并发" in profile.keywords
