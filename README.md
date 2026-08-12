# AI Interview Agent Runtime

This repository is a staged refactor target for the existing digital-human interview system.
It does not copy Kugelblitz or MindBridge code. It keeps the interview domain as the core
abstraction and removes LangGraph from the core runtime.

## Goal

Build an artifact-driven interview runtime:

```text
State -> Agent -> Skill -> Authorized Tools -> Artifact -> Blackboard -> Transition -> Checkpoint/Event
```

The first phase contains a minimal runnable loop:

```text
Start Session -> Generate Question -> Receive Answer -> Evaluate -> Follow-up / Next Question -> Checkpoint -> Finish
```

## Run Tests

```powershell
cd D:\agent项目学习\AI面试
python -m pytest
```

The tests use mock agents and do not require an LLM, Qdrant, Redis, MySQL, or the digital-human vendor APIs.
