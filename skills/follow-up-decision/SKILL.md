---
name: follow-up-decision
description: Decide whether a follow-up question is useful.
agent: FollowUpAgent
tools:
  - rubric.retrieve
  - knowledge.retrieve
output_schema: FollowUpDecisionArtifact
timeout: 2
retry: 0
max_tokens: 800
execution_strategy: structured_llm
version: 1.0
---

Inspect evaluation evidence and missing points, then return a structured follow-up decision.
