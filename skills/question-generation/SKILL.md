---
name: question-generation
description: Generate or retrieve interview questions.
agent: QuestionAgent
tools:
  - question_bank.search
  - knowledge.retrieve
  - resume.retrieve
  - jd.retrieve
output_schema: QuestionArtifact
timeout: 15
retry: 1
max_tokens: 2500
execution_strategy: deterministic
version: 1.0
---

Select the next interview question from the plan, candidate profile, JD, prior questions,
and existing evidence. Prefer grounded question-bank candidates and fall back safely.
