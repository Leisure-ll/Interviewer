from __future__ import annotations

from interview_agent_runtime.domain import InterviewDimension, InterviewPlan


def test_interview_plan_releases_budget_when_dimension_completed():
    plan = InterviewPlan(
        dimensions=[
            InterviewDimension("Redis", 0.6, "advanced", 2, 1, 0.7, "hard", asked_questions=1),
            InterviewDimension("System Design", 0.4, "working", 1, 0, 0.7, "medium"),
        ],
        total_question_budget=3,
        total_follow_up_budget=1,
        estimated_duration_minutes=12,
    )

    released = plan.update_after_evaluation("Redis", 0.8, 2)

    assert released == 1
    assert plan.dimensions[0].completed is True
    assert plan.dimensions[1].question_budget == 2
