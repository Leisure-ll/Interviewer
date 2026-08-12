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
version: 1.0
---

Read resume and JD context, then produce structured candidate and position profiles.
