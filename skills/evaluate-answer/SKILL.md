---
name: evaluate-answer
description: Evaluate candidate answer with evidence.
agent: EvaluatorAgent
tools:
  - rubric.retrieve
  - knowledge.retrieve
  - answer.semantic_match
output_schema: EvaluationArtifact
timeout: 15
retry: 1
max_tokens: 2500
execution_strategy: structured_llm
version: 1.0
---

Evaluate the current answer against the current question and rubric.
Return only structured evidence, scores, missing points, strengths, and confidence.
Do not decide whether to ask a follow-up question.
