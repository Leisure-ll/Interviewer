from __future__ import annotations

from interview_agent_runtime.checkpoint import InMemoryCheckpointStore, JsonFileCheckpointStore
from interview_agent_runtime.harness import HarnessConfig, InterviewHarness
from interview_agent_runtime.observability import NoopObserver
from interview_agent_runtime.providers import FakeLLMProvider, OpenAICompatibleLLMProvider


def test_mock_harness_assembles_fake_dependencies():
    harness = InterviewHarness.from_config(HarnessConfig.mock())

    assert isinstance(harness.checkpoint_store, InMemoryCheckpointStore)
    assert isinstance(harness.llm_provider, FakeLLMProvider)
    assert isinstance(harness.observer, NoopObserver)


def test_development_harness_uses_injected_configured_provider_and_json_checkpoint(tmp_path):
    harness = InterviewHarness.from_config(
        HarnessConfig(
            mode="development",
            checkpoint_dir=tmp_path,
            llm_api_key="test-key",
            llm_base_url="http://localhost:9999/v1",
            llm_model="test-model",
        )
    )

    assert isinstance(harness.checkpoint_store, JsonFileCheckpointStore)
    assert isinstance(harness.llm_provider, OpenAICompatibleLLMProvider)
    assert harness.llm_provider.base_url == "http://localhost:9999/v1"
    assert harness.llm_provider.model == "test-model"
