from __future__ import annotations

import inspect

from interview_agent_runtime.agents import EvaluatorAgent, FollowUpAgent, PlannerAgent, ProfileAgent, QuestionAgent, ReportAgent


def test_agents_do_not_hold_other_agent_instances():
    agents = [ProfileAgent(), PlannerAgent(), QuestionAgent(), EvaluatorAgent(), FollowUpAgent(), ReportAgent()]
    agent_classes = tuple(type(item) for item in agents)

    for agent in agents:
        for value in vars(agent).values():
            assert not isinstance(value, agent_classes)


def test_agents_do_not_directly_call_other_agents():
    agent_names = ["ProfileAgent", "PlannerAgent", "QuestionAgent", "EvaluatorAgent", "FollowUpAgent", "ReportAgent"]
    for cls in [ProfileAgent, PlannerAgent, QuestionAgent, EvaluatorAgent, FollowUpAgent, ReportAgent]:
        source = inspect.getsource(cls)
        for other in agent_names:
            if other != cls.__name__:
                assert f"{other}(" not in source
