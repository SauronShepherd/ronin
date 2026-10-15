"""Pure, provider-neutral contracts for Ronin AI Studio."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import urlsplit


class AdapterKind(StrEnum):
    OLLAMA = "ollama"
    LLAMA_CPP = "llama_cpp"
    VLLM = "vllm"
    OPENAI_COMPATIBLE = "openai_compatible"


class DesiredState(StrEnum):
    ENABLED = "enabled"
    DISABLED = "disabled"


class ObservedState(StrEnum):
    UNKNOWN = "unknown"
    PROBING = "probing"
    READY = "ready"
    DEGRADED = "degraded"
    SATURATED = "saturated"
    FAILED = "failed"


class Capability(StrEnum):
    CHAT = "chat"
    COMPLETION = "completion"
    EMBEDDING = "embedding"
    RESPONSE = "response"
    STREAMING = "streaming"
    TOOLS = "tools"
    STRUCTURED_OUTPUT = "structured_output"
    VISION = "vision"
    AUDIO = "audio"
    RERANK = "rerank"


def _text(value: str, name: str, *, max_length: int = 128) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{name} must be non-empty and trimmed")
    if "\x00" in value or "\n" in value or "\r" in value:
        raise ValueError(f"{name} contains a control character")
    if len(value) > max_length:
        raise ValueError(f"{name} exceeds {max_length} characters")
    return value


@dataclass(frozen=True, slots=True, order=True)
class EndpointId:
    value: str

    def __post_init__(self) -> None:
        value = _text(self.value, "endpoint id")
        if value != value.casefold() or "/" in value or ".." in value:
            raise ValueError("endpoint id must be lowercase and path-safe")


@dataclass(frozen=True, slots=True, order=True)
class PublicModelName:
    value: str

    def __post_init__(self) -> None:
        value = _text(self.value, "public model name")
        if "/" in value or ".." in value:
            raise ValueError("public model name must be path-safe")


@dataclass(frozen=True, slots=True)
class RequestLimits:
    max_body_bytes: int = 4 * 1024 * 1024
    max_response_bytes: int = 16 * 1024 * 1024
    timeout_seconds: float = 120.0
    max_stream_seconds: float = 600.0
    max_stream_bytes: int = 64 * 1024 * 1024

    def __post_init__(self) -> None:
        if self.max_body_bytes < 1024 or self.max_response_bytes < 1024:
            raise ValueError("body and response limits must be at least 1024 bytes")
        if self.max_stream_bytes < self.max_response_bytes:
            raise ValueError("stream limit must cover a regular response")
        if self.timeout_seconds <= 0 or self.max_stream_seconds <= 0:
            raise ValueError("timeouts must be positive")
        if self.timeout_seconds > 600 or self.max_stream_seconds > 3600:
            raise ValueError("timeouts exceed the safety maximum")


@dataclass(frozen=True, slots=True)
class EndpointConfig:
    id: EndpointId
    adapter: AdapterKind
    base_url: str
    models: tuple[PublicModelName, ...]
    priority: int = 100
    weight: int = 1
    max_in_flight: int = 1
    desired_state: DesiredState = DesiredState.ENABLED
    allow_http: bool = True
    limits: RequestLimits = RequestLimits()

    def __post_init__(self) -> None:
        parsed = urlsplit(self.base_url)
        allowed_schemes = {"http", "https"} if self.allow_http else {"https"}
        if parsed.scheme not in allowed_schemes or not parsed.hostname:
            raise ValueError("endpoint URL must use an allowed HTTP(S) scheme")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("endpoint URL cannot contain credentials, query or fragment")
        if not self.models or len(set(self.models)) != len(self.models):
            raise ValueError("endpoint must advertise unique models")
        if self.priority < 0 or not 1 <= self.weight <= 10000:
            raise ValueError("priority/weight outside bounds")
        if not 1 <= self.max_in_flight <= 10000:
            raise ValueError("max_in_flight outside bounds")


@dataclass(frozen=True, slots=True)
class ModelSnapshot:
    endpoint_id: EndpointId
    provider_model_id: str
    public_name: PublicModelName
    capabilities: frozenset[Capability]
    context_window: int | None = None
    last_seen_at: str | None = None

    def __post_init__(self) -> None:
        _text(self.provider_model_id, "provider model id")
        if not self.capabilities:
            raise ValueError("model must advertise at least one capability")
        if self.context_window is not None and not 1 <= self.context_window <= 10_000_000:
            raise ValueError("context window outside bounds")


__all__ = [
    "AdapterKind",
    "Capability",
    "DesiredState",
    "EndpointConfig",
    "EndpointId",
    "ModelSnapshot",
    "ObservedState",
    "PublicModelName",
    "RequestLimits",
]
