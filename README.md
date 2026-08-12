# AI Interview Agent Runtime

This repository is a staged refactor target for the existing digital-human interview system.
It does not copy Kugelblitz or MindBridge code. It keeps the interview domain as the core
abstraction and removes LangGraph from the core runtime.

## Goal

Build an artifact-driven interview runtime:

```text
State -> Agent -> Skill -> Authorized Tools -> Artifact -> Blackboard -> Transition -> Checkpoint/Event
```

The current phase contains a runnable AI interview loop:

```text
Start Session -> Profile -> Plan -> Generate Question -> Answer -> Evaluate -> Evidence -> Follow-up / Next Question -> Report
```

## Domain Model

The runtime is driven by interview domain objects:

- `CandidateProfile`: skills, experience, strengths, potential gaps, resume keywords.
- `PositionProfile`: role, seniority, required/preferred skills, responsibilities, dimensions, keywords.
- `InterviewPlan`: weighted dimensions, difficulty, question budget, follow-up budget, duration.
- `QuestionArtifact`: text, dimension, type, source, expected points, related skills.
- `EvaluationArtifact`: score, strengths, missing points, confidence, evidence, follow-up intent.
- `CapabilityProfile`: verified, weak, and uncertain skills with coverage and evidence counts.
- `InterviewReportArtifact`: role match score, dimension scores, evidence, recommendation.

## Local Demo

```powershell
cd D:\agent项目学习\AI面试
python scripts\demo_interview.py
```

The demo simulates a Java backend / agent engineering interview without requiring an
LLM key. It uses mock tools for resume, JD, question bank, rubric, and knowledge retrieval.
It prints the interview plan, each question, the simulated answer, evaluation evidence,
missing points, follow-up decision, transition, and final report.

## Run Tests

```powershell
cd D:\agent项目学习\AI面试
python -m pytest
```

The tests cover profile construction, planning, question generation and fallback,
evidence-driven evaluation, follow-up guard, skill loading, tool governance,
checkpoint restore, and the full interview flow.

## Current Architecture

```text
InterviewRuntime
  -> FSM
  -> Specialist Agent
  -> Skill
  -> Authorized Tools
  -> Artifact
  -> Blackboard
  -> Evidence / CapabilityProfile
  -> Checkpoint / Event
```

Core runtime remains independent from FastAPI, LangGraph, Qdrant, Redis, MySQL, ASR,
TTS, and digital-human vendors. Those systems should be connected through adapters.

## Adaptive Interview

`PlannerAgent` builds an interview plan from candidate profile and position profile.
The plan is not static. After every evaluation, `InterviewPlanPolicy` updates dimension
coverage, marks sufficiently covered dimensions as complete, and releases unused
question budget to the remaining high-value dimensions.

`TransitionGuard` prevents the LLM/Agent output from directly controlling the flow.
Follow-up requires confidence, global budget, dimension budget, per-question round limit,
duplicate target filtering, and session timeout checks.

## Evidence-Driven Evaluation

`EvidenceDrivenEvaluator` does not return an isolated score. It derives:

- matched expected points
- missing points
- evidence with source question, answer excerpt, skill, confidence, and polarity
- score tied to evidence, missing points, and answer detail

The report is generated from `InterviewPlan`, `CapabilityProfile`, dimension scores,
and accumulated evidence, not from a plain chat transcript.

## Skill Runtime

`SkillRegistry.load_from_directory()` reads `skills/<name>/SKILL.md` frontmatter and
prompt text. Current skills:

- `profile-analysis`
- `interview-planning`
- `question-generation`
- `evaluate-answer`
- `follow-up-decision`
- `interview-report`

## Tool Governance

Tools remain behind `ToolRegistry` and `ToolPolicy`. Agent visible tools are computed by:

```text
Agent allowed tools ∩ Skill declared tools ∩ Session policy
```

The default tools are fake adapters for local execution. Real Qdrant, MySQL, Redis,
LLM, ASR, TTS, and digital-human integrations should be connected as adapters.

## Checkpoint Recovery

`JsonFileCheckpointStore` supports save/load of the interview blackboard, including:

- session inputs
- current stage and question
- candidate and position profiles
- interview plan
- answers, evaluations, evidence
- capability profile
- budget and follow-up state

## Application Service

`InterviewApplicationService` is the intended entry point for API, web, or digital-human
interaction layers:

- `start_interview(candidate_id, resume, jd)`
- `submit_answer(session_id, answer)`
- `resume_interview(session_id)`
- `get_status(session_id)`
- `get_report(session_id)`
