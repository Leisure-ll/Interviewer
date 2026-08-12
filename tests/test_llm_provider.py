from __future__ import annotations

import asyncio

import pytest

from interview_agent_runtime.providers import FakeLLMProvider, OpenAICompatibleLLMProvider, StructuredOutputError


def test_fake_llm_provider_returns_structured_output():
    asyncio.run(_fake_case())


async def _fake_case():
    provider = FakeLLMProvider(responses=[{"score": 80, "missing_points": []}])
    response = await provider.structured_generate(messages=[], output_schema="EvaluationDraft")

    assert response.parsed["score"] == 80
    assert response.model == "fake"


def test_fake_llm_provider_rejects_malformed_json():
    async def _case():
        provider = FakeLLMProvider(malformed=True)
        with pytest.raises(StructuredOutputError):
            await provider.structured_generate(messages=[], output_schema="EvaluationDraft")

    asyncio.run(_case())


def test_openai_compatible_provider_requires_key_before_network_call():
    async def _case():
        provider = OpenAICompatibleLLMProvider(api_key="", base_url="http://127.0.0.1:1", model="x")
        with pytest.raises(RuntimeError):
            await provider.structured_generate(messages=[], output_schema="Any", timeout=0.01)

    asyncio.run(_case())
