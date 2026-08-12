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
version: 1.0
---

Evaluate the current answer against the current question, rubric, and interview plan.
Return only structured evidence, scores, missing points, and follow-up intent.
