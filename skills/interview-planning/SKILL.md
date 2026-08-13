---
name: interview-planning
description: Create an adaptive interview plan.
agent: PlannerAgent
tools:
  - jd.retrieve
  - rubric.retrieve
output_schema: InterviewPlanArtifact
timeout: 8
retry: 1
max_tokens: 2000
execution_strategy: deterministic
version: 1.0
---

Use candidate profile, position requirements, seniority, and rubric to allocate dimensions,
weights, question budgets, follow-up budgets, and difficulty.
