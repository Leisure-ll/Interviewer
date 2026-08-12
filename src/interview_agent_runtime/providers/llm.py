from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Optional, Protocol


class StructuredOutputError(ValueError):
    pass


@dataclass
class LLMResponse:
    content: str
    parsed: dict[str, Any]
    model: str
    raw: dict[str, Any]


class LLMProvider(Protocol):
    async def structured_generate(
        self,
        *,
        messages: list[dict[str, str]],
        output_schema: str,
        timeout: Optional[float] = None,
    ) -> LLMResponse:
        ...


class FakeLLMProvider:
    def __init__(self, responses: Optional[list[dict[str, Any]]] = None, malformed: bool = False) -> None:
        self.responses = list(responses or [])
        self.malformed = malformed
        self.calls: list[dict[str, Any]] = []

    async def structured_generate(
        self,
        *,
        messages: list[dict[str, str]],
        output_schema: str,
        timeout: Optional[float] = None,
    ) -> LLMResponse:
        self.calls.append({"messages": messages, "output_schema": output_schema, "timeout": timeout})
        if self.malformed:
            return _parse_response("not-json", model="fake", raw={}, output_schema=output_schema)
        payload = self.responses.pop(0) if self.responses else {}
        content = json.dumps(payload, ensure_ascii=False)
        return _parse_response(content, model="fake", raw={"content": content}, output_schema=output_schema)


class OpenAICompatibleLLMProvider:
    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        self.api_key = os.getenv("OPENAI_API_KEY") if api_key is None else api_key
        self.base_url = (base_url if base_url is not None else os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
        self.model = model if model is not None else os.getenv("OPENAI_MODEL") or "gpt-4o-mini"

    async def structured_generate(
        self,
        *,
        messages: list[dict[str, str]],
        output_schema: str,
        timeout: Optional[float] = None,
    ) -> LLMResponse:
        if not self.api_key:
            raise RuntimeError("LLM api_key is required")
        loop = asyncio.get_event_loop()
        return await asyncio.wait_for(
            loop.run_in_executor(None, self._request, messages, output_schema, timeout),
            timeout=timeout,
        )

    def _request(
        self,
        messages: list[dict[str, str]],
        output_schema: str,
        timeout: Optional[float],
    ) -> LLMResponse:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout or 30) as response:
                raw = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"LLM HTTP {exc.code}: {body}") from exc
        content = raw["choices"][0]["message"]["content"]
        return _parse_response(content, model=self.model, raw=raw, output_schema=output_schema)


def _parse_response(content: str, model: str, raw: dict[str, Any], output_schema: str) -> LLMResponse:
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise StructuredOutputError(f"Malformed structured output for {output_schema}") from exc
    if not isinstance(parsed, dict):
        raise StructuredOutputError(f"Structured output for {output_schema} must be a JSON object")
    return LLMResponse(content=content, parsed=parsed, model=model, raw=raw)
