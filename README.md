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

## Local Demo

```powershell
cd D:\agent项目学习\AI面试
python scripts\demo_interview.py
```

The demo simulates a Java backend / agent engineering interview without requiring an
LLM key. It uses mock tools for resume, JD, question bank, rubric, and knowledge retrieval.

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
