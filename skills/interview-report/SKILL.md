---
name: interview-report
description: Generate evidence-driven interview report.
agent: ReportAgent
tools:
  - evaluation.history
  - evidence.aggregate
output_schema: InterviewReportArtifact
timeout: 20
retry: 1
max_tokens: 2500
execution_strategy: structured_llm
version: 1.0
---

Build final report from interview plan, capability profile, dimension scores, and evidence.
