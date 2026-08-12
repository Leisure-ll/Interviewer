from __future__ import annotations

import asyncio

import pytest

from interview_agent_runtime.artifacts import QuestionArtifact
from conftest import make_mock_runtime


def test_runtime_rejects_skill_output_schema_mismatch():
    runtime = make_mock_runtime()
    artifact = QuestionArtifact(
        owner="QuestionAgent",
        question_id="q1",
        title="请说明缓存一致性",
        dimension="Java Backend",
    )

    with pytest.raises(TypeError):
        runtime._validate_artifact_schema(artifact, "EvaluationArtifact")
