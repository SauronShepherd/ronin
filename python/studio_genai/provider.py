"""Provider-neutral GenAI execution contracts and OpenAI-compatible HTTP adapter."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol, runtime_checkable
from urllib.parse import urlsplit

from studio_core.genai import GenAIModel, ModelProvider
from studio_storage.secrets import SecretResolver

ChatRole = Literal["system", "user", "assistant"]


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: ChatRole
    content: str

    def __post_init__(self) -> None:
        if self.role not in {"system", "user", "assistant"}:
            raise ValueError("unsupported chat role")
        if not self.content or "\x00" in self.content:
            raise ValueError("chat content must be non-empty")


@dataclass(frozen=True, slots=True)
class ChatResult:
    content: str
    model_id: str
    input_tokens: int | None = None
    output_tokens: int | None = None

    def __post_init__(self) -> None:
        if not self.content:
            raise ValueError("chat result content must be non-empty")
        if not self.model_id:
            raise ValueError("chat result model_id must be non-empty")
        for value in (self.input_tokens, self.output_tokens):
            if value is not None and value < 0:
                raise ValueError("token counts must be non-negative")


@dataclass(frozen=True, slots=True)
class EmbeddingResult:
    vectors: tuple[tuple[float, ...], ...]
    model_id: str

    def __post_init__(self) -> None:
        if not self.vectors:
            raise ValueError("embedding result requires at least one vector")
        dimensions = {len(vector) for vector in self.vectors}
        if len(dimensions) != 1 or 0 in dimensions:
            raise ValueError("embedding vectors must share a positive dimension")
        for vector in self.vectors:
            if any(value != value or value in (float("inf"), float("-inf")) for value in vector):
                raise ValueError("embedding values must be finite")
        if not self.model_id:
            raise ValueError("embedding result model_id must be non-empty")


@runtime_checkable
class GenAIProviderRuntime(Protocol):
    def chat(self, model: GenAIModel, messages: Sequence[ChatMessage]) -> ChatResult: ...

    def embed(self, model: GenAIModel, texts: Sequence[str]) -> EmbeddingResult: ...


class GenAIProviderDependencyError(RuntimeError):
    """Raised when the optional HTTP runtime is unavailable."""


def _httpx() -> Any:
    try:
        import httpx
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise GenAIProviderDependencyError(
            "OpenAI-compatible GenAI support requires httpx from optional data-plane dependencies"
        ) from exc
    return httpx


def _properties(provider: ModelProvider) -> dict[str, str]:
    return dict(provider.properties)


class OpenAICompatibleProvider:
    """Minimal chat-completions/embeddings adapter for OpenAI-compatible endpoints.

    The adapter intentionally targets the widely implemented compatibility wire shape,
    not provider-specific tool/response extensions. Endpoint/model selection stays in
    Ronin metadata and credentials are resolved only at this execution boundary.
    """

    def __init__(self, provider: ModelProvider, secrets: SecretResolver) -> None:
        if provider.adapter not in {"openai-compatible", "openai_compatible"}:
            raise ValueError("provider metadata does not target the OpenAI-compatible adapter")
        if provider.endpoint is None:
            raise ValueError("OpenAI-compatible provider requires an endpoint")
        parsed = urlsplit(provider.endpoint)
        properties = _properties(provider)
        allow_http = properties.get("allow_http", "false").casefold() == "true"
        allowed = {"https", "http"} if allow_http else {"https"}
        if parsed.scheme not in allowed or not parsed.hostname:
            raise ValueError("provider endpoint must use HTTPS unless allow_http=true")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("provider endpoint must not embed credentials")
        if parsed.query or parsed.fragment:
            raise ValueError("provider endpoint must not contain query or fragment")
        self._provider = provider
        self._secrets = secrets
        self._base_url = provider.endpoint.rstrip("/")
        try:
            timeout = float(properties.get("timeout_seconds", "60"))
        except ValueError as exc:
            raise ValueError("provider timeout_seconds must be numeric") from exc
        if timeout <= 0 or timeout > 600:
            raise ValueError("provider timeout_seconds must be in (0, 600]")
        self._timeout = timeout

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self._provider.secret_ref is not None:
            token = self._secrets.resolve(self._provider.secret_ref).reveal_text()
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _require_model(self, model: GenAIModel, capability: str) -> None:
        if model.provider_id != self._provider.id:
            raise ValueError("GenAI model belongs to a different provider")
        if capability not in model.capabilities:
            raise ValueError(f"GenAI model does not advertise {capability} capability")

    def chat(self, model: GenAIModel, messages: Sequence[ChatMessage]) -> ChatResult:
        self._require_model(model, "chat")
        if not messages:
            raise ValueError("chat requires at least one message")
        httpx = _httpx()
        payload = {
            "model": model.model_id,
            "messages": [{"role": item.role, "content": item.content} for item in messages],
        }
        with httpx.Client(follow_redirects=False, timeout=self._timeout) as client:
            response = client.post(
                f"{self._base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
            )
            response.raise_for_status()
            body = response.json()
        if not isinstance(body, dict):
            raise ValueError("chat provider response must be an object")
        choices = body.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ValueError("chat provider response has no choices")
        first = choices[0]
        if not isinstance(first, dict):
            raise ValueError("chat provider choice has invalid shape")
        message = first.get("message")
        if not isinstance(message, dict) or not isinstance(message.get("content"), str):
            raise ValueError("chat provider response has no text content")
        usage = body.get("usage")
        input_tokens = None
        output_tokens = None
        if isinstance(usage, dict):
            prompt_tokens = usage.get("prompt_tokens")
            completion_tokens = usage.get("completion_tokens")
            if isinstance(prompt_tokens, int) and not isinstance(prompt_tokens, bool):
                input_tokens = prompt_tokens
            if isinstance(completion_tokens, int) and not isinstance(completion_tokens, bool):
                output_tokens = completion_tokens
        returned_model = body.get("model")
        return ChatResult(
            message["content"],
            returned_model if isinstance(returned_model, str) else model.model_id,
            input_tokens,
            output_tokens,
        )

    def embed(self, model: GenAIModel, texts: Sequence[str]) -> EmbeddingResult:
        self._require_model(model, "embedding")
        if not texts or len(texts) > 2048:
            raise ValueError("embedding request must contain between 1 and 2048 texts")
        normalized = tuple(text for text in texts if text and "\x00" not in text)
        if len(normalized) != len(texts):
            raise ValueError("embedding texts must be non-empty and contain no NUL")
        httpx = _httpx()
        with httpx.Client(follow_redirects=False, timeout=self._timeout) as client:
            response = client.post(
                f"{self._base_url}/embeddings",
                headers=self._headers(),
                json={"model": model.model_id, "input": list(normalized)},
            )
            response.raise_for_status()
            body = response.json()
        if not isinstance(body, dict) or not isinstance(body.get("data"), list):
            raise ValueError("embedding provider response has invalid shape")
        data = body["data"]
        ordered: list[tuple[int, tuple[float, ...]]] = []
        for position, item in enumerate(data):
            if not isinstance(item, dict) or not isinstance(item.get("embedding"), list):
                raise ValueError("embedding provider item has invalid shape")
            index = item.get("index", position)
            if not isinstance(index, int) or isinstance(index, bool):
                raise ValueError("embedding provider item index must be integer")
            raw = item["embedding"]
            if not all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in raw):
                raise ValueError("embedding vector must contain only numeric values")
            ordered.append((index, tuple(float(value) for value in raw)))
        ordered.sort(key=lambda item: item[0])
        if len(ordered) != len(normalized):
            raise ValueError("embedding provider returned unexpected vector count")
        returned_model = body.get("model")
        return EmbeddingResult(
            tuple(vector for _, vector in ordered),
            returned_model if isinstance(returned_model, str) else model.model_id,
        )


__all__ = (
    "ChatMessage",
    "ChatResult",
    "EmbeddingResult",
    "GenAIProviderDependencyError",
    "GenAIProviderRuntime",
    "OpenAICompatibleProvider",
)
