"""Provider adapter contracts and bounded OpenAI-compatible discovery."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from .contracts import Capability, EndpointConfig, ModelSnapshot, PublicModelName


class Transport(Protocol):
    def get(self, url: str, *, timeout: float) -> tuple[int, Mapping[str, Any]]: ...


@dataclass(frozen=True, slots=True)
class CapabilitySnapshot:
    ready: bool
    has_capacity: bool | None
    models: tuple[ModelSnapshot, ...]
    detail: str = ""


class AdapterError(RuntimeError):
    """The provider response cannot be trusted or is unavailable."""


def _string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise AdapterError(f"provider field {field!r} must be a non-empty string")
    return value


class OpenAICompatibleAdapter:
    """Readiness and model discovery for OpenAI-compatible servers."""

    def __init__(self, transport: Transport, *, timeout: float = 5.0) -> None:
        if timeout <= 0 or timeout > 60:
            raise ValueError("probe timeout must be in (0, 60]")
        self._transport = transport
        self._timeout = timeout

    def probe(self, endpoint: EndpointConfig) -> CapabilitySnapshot:
        base = endpoint.base_url.rstrip("/")
        status, body = self._transport.get(f"{base}/v1/models", timeout=self._timeout)
        if status >= 500:
            raise AdapterError(f"provider returned status {status}")
        if status != 200:
            raise AdapterError(f"provider model discovery failed with status {status}")
        raw_models = body.get("data")
        if not isinstance(raw_models, list):
            raise AdapterError("provider models response has invalid data")
        models: list[ModelSnapshot] = []
        for raw in raw_models:
            if not isinstance(raw, Mapping):
                raise AdapterError("provider model item is not an object")
            provider_id = _string(raw.get("id"), "id")
            public_name = PublicModelName(provider_id)
            models.append(
                ModelSnapshot(
                    endpoint.id,
                    provider_id,
                    public_name,
                    frozenset({Capability.CHAT, Capability.COMPLETION, Capability.RESPONSE}),
                )
            )
        return CapabilitySnapshot(True, None, tuple(models), "models discovered")


class OllamaAdapter(OpenAICompatibleAdapter):
    """Ollama's OpenAI-compatible surface with conservative capabilities."""


class VLLMAdapter(OpenAICompatibleAdapter):
    """vLLM profile; vendor extensions remain opt-in at request validation."""


class LlamaCppAdapter(OpenAICompatibleAdapter):
    """llama.cpp profile; readiness and slot capacity are separate probes."""

    def probe(self, endpoint: EndpointConfig) -> CapabilitySnapshot:
        snapshot = super().probe(endpoint)
        status, _body = self._transport.get(
            f"{endpoint.base_url.rstrip('/')}/health", timeout=self._timeout
        )
        if status != 200:
            return CapabilitySnapshot(False, None, snapshot.models, "llama.cpp is not ready")
        return snapshot


__all__ = [
    "AdapterError", "CapabilitySnapshot", "LlamaCppAdapter", "OllamaAdapter",
    "OpenAICompatibleAdapter", "Transport", "VLLMAdapter",
]
