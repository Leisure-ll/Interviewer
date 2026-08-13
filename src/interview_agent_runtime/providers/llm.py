from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol, Union

from interview_agent_runtime.errors import LLMProviderError
from interview_agent_runtime.messages import AgentMessage, MessageRole, ToolCall
from interview_agent_runtime.tools import ToolSpec


class StructuredOutputError(ValueError):
    pass


@dataclass
class LLMRequest:
    messages: list[AgentMessage]
    tools: list[ToolSpec] = field(default_factory=list)
    response_schema: Optional[str] = None
    temperature: float = 0.2
    max_tokens: Optional[int] = None
    timeout: Optional[float] = None


@dataclass
class LLMResponse:
    message: AgentMessage
    model: str
    finish_reason: str = "stop"
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def content(self) -> str:
        return self.message.content or ""

    @property
    def parsed(self) -> dict[str, Any]:
        try:
            value = json.loads(self.content)
        except json.JSONDecodeError as exc:
            raise StructuredOutputError("LLM response is not valid JSON") from exc
        if not isinstance(value, dict):
            raise StructuredOutputError("Structured output must be a JSON object")
        return value


class LLMProvider(Protocol):
    async def chat(self, request: LLMRequest) -> LLMResponse:
        ...

    async def structured_generate(
        self,
        *,
        messages: list[Union[AgentMessage, dict[str, str]]],
        output_schema: str,
        timeout: Optional[float] = None,
    ) -> LLMResponse:
        ...


class FakeLLMProvider:
    """Scriptable provider for both structured output and AgentLoop tests."""

    def __init__(
        self,
        responses: Optional[list[Any]] = None,
        malformed: bool = False,
    ) -> None:
        self.responses = list(responses or [])
        self.malformed = malformed
        self.calls: list[dict[str, Any]] = []
        self.requests: list[LLMRequest] = []

    async def chat(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        self.calls.append(
            {
                "messages": request.messages,
                "tools": request.tools,
                "output_schema": request.response_schema,
                "timeout": request.timeout,
            }
        )
        if not self.responses:
            return _scripted_response({}, model="fake", malformed=self.malformed)
        scripted = self.responses.pop(0)
        return _scripted_response(scripted, model="fake", malformed=self.malformed)

    async def structured_generate(
        self,
        *,
        messages: list[Union[AgentMessage, dict[str, str]]],
        output_schema: str,
        timeout: Optional[float] = None,
    ) -> LLMResponse:
        normalized = [_coerce_message(item) for item in messages]
        response = await self.chat(
            LLMRequest(
                messages=normalized,
                response_schema=output_schema,
                timeout=timeout,
            )
        )
        _ = response.parsed
        return response


class OpenAICompatibleLLMProvider:
    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        self.api_key = os.getenv("OPENAI_API_KEY") if api_key is None else api_key
        self.base_url = (
            base_url
            if base_url is not None
            else os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1"
        ).rstrip("/")
        self.model = model if model is not None else os.getenv("OPENAI_MODEL") or "gpt-4o-mini"

    async def chat(self, request: LLMRequest) -> LLMResponse:
        if not self.api_key:
            raise LLMProviderError("LLM api_key is required")
        loop = asyncio.get_event_loop()
        try:
            return await asyncio.wait_for(
                loop.run_in_executor(None, self._request, request),
                timeout=request.timeout,
            )
        except asyncio.TimeoutError:
            raise
        except LLMProviderError:
            raise
        except Exception as exc:
            raise LLMProviderError("OpenAI-compatible LLM request failed") from exc

    async def structured_generate(
        self,
        *,
        messages: list[Union[AgentMessage, dict[str, str]]],
        output_schema: str,
        timeout: Optional[float] = None,
    ) -> LLMResponse:
        response = await self.chat(
            LLMRequest(
                messages=[_coerce_message(item) for item in messages],
                response_schema=output_schema,
                timeout=timeout,
            )
        )
        _ = response.parsed
        return response

    def _request(self, request: LLMRequest) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [message.to_dict() for message in request.messages],
            "temperature": request.temperature,
        }
        if request.tools:
            payload["tools"] = [tool.to_provider_schema() for tool in request.tools]
        if request.response_schema:
            payload["response_format"] = {"type": "json_object"}
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens

        http_request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                http_request,
                timeout=request.timeout or 30,
            ) as response:
                raw = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise LLMProviderError(f"LLM HTTP {exc.code}: {body}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise LLMProviderError("LLM network request failed") from exc

        try:
            choice = raw["choices"][0]
            raw_message = choice["message"]
            message = _message_from_provider(raw_message)
            usage = raw.get("usage", {})
            return LLMResponse(
                message=message,
                model=raw.get("model", self.model),
                finish_reason=choice.get("finish_reason", "stop"),
                prompt_tokens=int(usage.get("prompt_tokens", 0) or 0),
                completion_tokens=int(usage.get("completion_tokens", 0) or 0),
                total_tokens=int(usage.get("total_tokens", 0) or 0),
                raw=raw,
            )
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise LLMProviderError("Malformed LLM response") from exc


def _coerce_message(value: Union[AgentMessage, dict[str, str]]) -> AgentMessage:
    if isinstance(value, AgentMessage):
        return value
    return AgentMessage(
        role=MessageRole(value["role"]),
        content=value.get("content"),
    )


def _scripted_response(value: Any, model: str, malformed: bool = False) -> LLMResponse:
    if isinstance(value, LLMResponse):
        return value
    if isinstance(value, AgentMessage):
        return LLMResponse(message=value, model=model, raw={})
    if isinstance(value, dict) and isinstance(value.get("message"), AgentMessage):
        return LLMResponse(
            message=value["message"],
            model=model,
            finish_reason=value.get("finish_reason", "stop"),
            raw=value.get("raw", {}),
        )
    if isinstance(value, dict) and "tool_calls" in value:
        calls = [
            ToolCall(
                id=str(item.get("id", f"call_{index}")),
                name=str(item["name"]),
                arguments=dict(item.get("arguments", {})),
            )
            for index, item in enumerate(value.get("tool_calls", []))
        ]
        return LLMResponse(
            message=AgentMessage.assistant(
                content=value.get("content"),
                tool_calls=calls,
            ),
            model=model,
            finish_reason=value.get("finish_reason", "tool_calls"),
            raw=value,
        )
    if isinstance(value, dict) and "content" in value:
        return LLMResponse(
            message=AgentMessage.assistant(content=str(value.get("content") or "")),
            model=model,
            finish_reason=value.get("finish_reason", "stop"),
            raw=value,
        )
    if malformed:
        content = "not-json"
    else:
        content = json.dumps(value, ensure_ascii=False)
    return LLMResponse(
        message=AgentMessage.assistant(content),
        model=model,
        raw={"content": content},
    )


def _message_from_provider(raw: dict[str, Any]) -> AgentMessage:
    tool_calls: list[ToolCall] = []
    for item in raw.get("tool_calls", []) or []:
        function = item.get("function", {})
        arguments = function.get("arguments", {})
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError as exc:
                raise LLMProviderError("Malformed tool call arguments") from exc
        if not isinstance(arguments, dict):
            raise LLMProviderError("Tool call arguments must be an object")
        tool_calls.append(
            ToolCall(
                id=str(item.get("id", "")),
                name=str(function.get("name", "")),
                arguments=arguments,
            )
        )
    return AgentMessage(
        role=MessageRole.ASSISTANT,
        content=raw.get("content"),
        tool_calls=tool_calls,
    )
