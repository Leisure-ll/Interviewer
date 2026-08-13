---
name: profile-analysis
description: Build candidate and position profiles.
agent: ProfileAgent
tools:
  - resume.retrieve
  - jd.retrieve
output_schema: CandidateProfileArtifact
timeout: 8
retry: 1
max_tokens: 2000
execution_strategy: react
max_iterations: 4
max_tool_calls: 4
version: 1.0
---

Read resume and JD context, then produce structured candidate and position profiles.
