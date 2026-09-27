"""Small, provider-neutral proxy for local OpenAI-compatible model servers.

The proxy deliberately does not implement an inference engine. Ollama,
llama.cpp, vLLM and other local servers remain independently deployable;
Ronin owns discovery metadata, routing policy, bounds and observability.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True, slots=True)
class LocalModelEndpoint:
    id: str
    base_url: str
    models: tuple[str, ...]
    priority: int = 100
    weight: int = 1
    enabled: bool = True
    allow_http: bool = True

    def __post_init__(self) -> None:
        if not self.id or self.id != self.id.strip() or "\x00" in self.id:
            raise ValueError("endpoint id must be non-empty and safe")
        parsed = urlsplit(self.base_url)
        if parsed.scheme not in ({"http", "https"} if self.allow_http else {"https"}):
            raise ValueError("endpoint URL must use HTTP(S) according to allow_http")
        if (
            not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("endpoint URL must contain only scheme, host and optional path")
        if not self.models or any(not model or "/" in model for model in self.models):
            raise ValueError("endpoint must advertise at least one safe model")
        if self.weight < 1 or self.priority < 0:
            raise ValueError("priority and weight must be positive")


@dataclass(frozen=True, slots=True)
class RoutingPolicy:
    """Deterministic routing controls; no content-based routing by default."""

    strategy: str = "priority"
    max_body_bytes: int = 4 * 1024 * 1024
    timeout_seconds: float = 120.0
    retries: int = 1

    def __post_init__(self) -> None:
        if self.strategy not in {"priority", "round_robin"}:
            raise ValueError("unsupported routing strategy")
        if self.max_body_bytes < 1024 or self.timeout_seconds <= 0 or self.retries < 0:
            raise ValueError("invalid proxy bounds")


class LocalModelProxy:
    """Select a local endpoint and forward an OpenAI-compatible JSON request."""

    def __init__(
        self,
        endpoints: Sequence[LocalModelEndpoint],
        *,
        policy: RoutingPolicy | None = None,
        transport: Callable[..., tuple[int, Mapping[str, object]]] | None = None,
    ) -> None:
        self._endpoints = tuple(endpoints)
        if not self._endpoints:
            raise ValueError("proxy requires at least one endpoint")
        self._policy = policy or RoutingPolicy()
        self._transport = transport or self._http_transport
        self._cursor = 0

    def resolve(self, model: str) -> LocalModelEndpoint:
        candidates = [e for e in self._endpoints if e.enabled and model in e.models]
        if not candidates:
            raise LookupError(f"no enabled local endpoint serves model {model!r}")
        if self._policy.strategy == "priority":
            return min(candidates, key=lambda endpoint: (endpoint.priority, endpoint.id))
        ordered = sorted(candidates, key=lambda endpoint: endpoint.id)
        endpoint = ordered[self._cursor % len(ordered)]
        self._cursor += 1
        return endpoint

    def forward(self, path: str, payload: Mapping[str, object]) -> tuple[int, Mapping[str, object]]:
        model = payload.get("model")
        if not isinstance(model, str) or not model:
            raise ValueError("OpenAI-compatible payload requires a model")
        if path not in {"/chat/completions", "/completions", "/embeddings", "/responses"}:
            raise ValueError("proxy path is not in the supported safe allowlist")
        raw = json.dumps(payload, separators=(",", ":")).encode()
        if len(raw) > self._policy.max_body_bytes:
            raise ValueError("request body exceeds proxy limit")
        endpoint = self.resolve(model)
        last_error: Exception | None = None
        for _attempt in range(self._policy.retries + 1):
            try:
                return self._transport(endpoint, path, payload, self._policy.timeout_seconds)
            except Exception as exc:  # retry only the selected endpoint deterministically
                last_error = exc
        if last_error is None:  # pragma: no cover - loop always runs at least once
            raise RuntimeError("proxy transport failed without an error")
        raise last_error

    @staticmethod
    def _http_transport(
        endpoint: LocalModelEndpoint, path: str, payload: Mapping[str, object], timeout: float
    ) -> tuple[int, Mapping[str, object]]:
        try:
            import httpx
        except ImportError as exc:  # pragma: no cover - optional runtime
            raise RuntimeError("local AI proxy requires httpx") from exc
        with httpx.Client(follow_redirects=False, timeout=timeout) as client:
            response = client.post(f"{endpoint.base_url.rstrip('/')}/v1{path}", json=payload)
            response.raise_for_status()
            body = response.json()
        if not isinstance(body, dict):
            raise ValueError("local endpoint response must be a JSON object")
        return response.status_code, body
