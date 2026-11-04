"""Stable interface for swappable local language-model runtimes.

The rest of PetLink should depend on ``LocalModelProvider`` rather than on a
specific runtime.  ``OpenAICompatibleProvider`` works with local servers such
as Ollama, LM Studio, llama.cpp server, and vLLM when their compatible API is
enabled.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Iterator, Mapping, Protocol, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class ModelError(RuntimeError):
    """A model could not be reached or returned an unusable response."""


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str


@dataclass(frozen=True)
class ModelConfig:
    """Connection and generation settings for one local model."""

    base_url: str
    model: str
    api_key: str | None = None
    timeout_seconds: float = 60.0
    temperature: float = 0.2
    max_tokens: int | None = None
    extra: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ModelResponse:
    text: str
    model: str | None = None
    raw: Mapping[str, Any] = field(default_factory=dict)


class LocalModelProvider(Protocol):
    """The only model contract the orchestrator should use."""

    @property
    def name(self) -> str: ...

    def complete(
        self,
        messages: Sequence[ChatMessage],
        *,
        response_format: Mapping[str, Any] | None = None,
    ) -> ModelResponse: ...

    def stream(
        self,
        messages: Sequence[ChatMessage],
        *,
        response_format: Mapping[str, Any] | None = None,
    ) -> Iterator[str]: ...

    def health_check(self) -> bool: ...


class OpenAICompatibleProvider:
    """Provider for local runtimes exposing ``/v1/chat/completions``."""

    def __init__(self, config: ModelConfig) -> None:
        self.config = config

    @property
    def name(self) -> str:
        return f"{self.config.base_url.rstrip('/')}/{self.config.model}"

    def complete(
        self,
        messages: Sequence[ChatMessage],
        *,
        response_format: Mapping[str, Any] | None = None,
    ) -> ModelResponse:
        payload = self._payload(messages, response_format=response_format)
        data = self._request("/chat/completions", payload)
        try:
            choice = data["choices"][0]
            message = choice["message"]
            text = message["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ModelError("The model returned an invalid chat response") from exc
        return ModelResponse(text=text, model=data.get("model"), raw=data)

    def stream(
        self,
        messages: Sequence[ChatMessage],
        *,
        response_format: Mapping[str, Any] | None = None,
    ) -> Iterator[str]:
        payload = self._payload(messages, response_format=response_format)
        payload["stream"] = True
        request = self._request_object("/chat/completions", payload)
        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:
                for raw_line in response:
                    line = raw_line.decode("utf-8").strip()
                    if line == "data: [DONE]":
                        return
                    if not line:
                        continue
                    if not line.startswith("data: "):
                        continue
                    try:
                        chunk = json.loads(line[6:])
                        if "error" in chunk:
                            raise ModelError("The model reported a streaming error")
                        choices = chunk.get("choices", [])
                        if not choices:
                            continue
                        content = choices[0].get("delta", {}).get("content")
                        if content is not None:
                            if not isinstance(content, str):
                                raise ModelError("The model returned non-text content")
                            yield content
                    except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
                        raise ModelError("The model returned an invalid stream chunk") from exc
        except (HTTPError, URLError, TimeoutError) as exc:
            raise ModelError(f"Could not reach local model at {self.config.base_url}") from exc

    def health_check(self) -> bool:
        try:
            self._request("/models", None)
            return True
        except ModelError:
            return False

    def _payload(
        self,
        messages: Sequence[ChatMessage],
        *,
        response_format: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": self.config.temperature,
            **self.config.extra,
        }
        if self.config.max_tokens is not None:
            payload["max_tokens"] = self.config.max_tokens
        if response_format is not None:
            payload["response_format"] = dict(response_format)
        return payload

    def _request_object(self, path: str, payload: Mapping[str, Any] | None) -> Request:
        url = f"{self.config.base_url.rstrip('/')}/v1{path}"
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {"Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        return Request(url, data=body, headers=headers, method="POST" if body else "GET")

    def _request(self, path: str, payload: Mapping[str, Any] | None) -> dict[str, Any]:
        request = self._request_object(path, payload)
        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise ModelError(f"Could not reach local model at {self.config.base_url}") from exc
        if not isinstance(data, dict):
            raise ModelError("The model returned an invalid JSON response")
        return data


class GoogleGeminiProvider:
    """Provider for Google's Gemini generateContent REST API."""

    def __init__(self, config: ModelConfig) -> None:
        self.config = config

    @property
    def name(self) -> str:
        return f"google/{self.config.model}"

    def complete(
        self,
        messages: Sequence[ChatMessage],
        *,
        response_format: Mapping[str, Any] | None = None,
    ) -> ModelResponse:
        contents = []
        for message in messages:
            role = "user" if message.role == "user" else "model"
            contents.append({"role": role, "parts": [{"text": message.content}]})
        body: dict[str, Any] = {"contents": contents}
        body["generationConfig"] = {"temperature": self.config.temperature}
        if response_format and response_format.get("type") == "json_object":
            body["generationConfig"]["responseMimeType"] = "application/json"

        url = f"{self.config.base_url.rstrip('/')}/v1beta/models/{self.config.model}:generateContent?key={self.config.api_key or ''}"
        request = Request(url, data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise ModelError("Could not reach the Google Gemini API") from exc
        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ModelError("Google Gemini returned an invalid response") from exc
        return ModelResponse(text=text, model=self.config.model, raw=data)

    def stream(self, messages: Sequence[ChatMessage], *, response_format: Mapping[str, Any] | None = None) -> Iterator[str]:
        yield self.complete(messages, response_format=response_format).text

    def health_check(self) -> bool:
        try:
            self.complete([ChatMessage("user", "Reply with OK")])
            return True
        except ModelError:
            return False


def create_provider(provider: str, config: ModelConfig) -> LocalModelProvider:
    """Build a provider from a user-facing provider name."""
    normalized = provider.strip().lower()
    if normalized in {"openai", "grok", "xai", "ollama", "lm-studio", "llama.cpp", "vllm"}:
        return OpenAICompatibleProvider(config)
    if normalized in {"google", "gemini", "google-gemini"}:
        return GoogleGeminiProvider(config)
    raise ValueError(f"Unsupported model provider: {provider}")
