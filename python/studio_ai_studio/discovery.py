"""Deterministic discovery orchestration for AI Studio endpoints."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .adapters import (
    CapabilitySnapshot,
    LlamaCppAdapter,
    OllamaAdapter,
    OpenAICompatibleAdapter,
    Transport,
    VLLMAdapter,
)
from .contracts import AdapterKind, EndpointConfig, ObservedState
from .state import ProbeObservation, transition
from .storage import SQLiteAIStudioStore


class Adapter(Protocol):
    def probe(self, endpoint: EndpointConfig) -> CapabilitySnapshot: ...


@dataclass(frozen=True, slots=True)
class DiscoveryResult:
    endpoint_id: str
    state: ObservedState
    model_count: int
    detail: str


class DiscoveryWorker:
    """Runs one bounded probe; scheduling/leases remain host responsibilities."""

    def __init__(
        self, store: SQLiteAIStudioStore, transport: Transport, *, timeout: float = 5.0
    ) -> None:
        self._store = store
        self._transport = transport
        self._timeout = timeout

    def _adapter(self, kind: AdapterKind) -> Adapter:
        adapters = {
            AdapterKind.OLLAMA: OllamaAdapter,
            AdapterKind.LLAMA_CPP: LlamaCppAdapter,
            AdapterKind.VLLM: VLLMAdapter,
            AdapterKind.OPENAI_COMPATIBLE: OpenAICompatibleAdapter,
        }
        return adapters[kind](self._transport, timeout=self._timeout)

    def probe(self, endpoint: EndpointConfig) -> DiscoveryResult:
        self._store.set_observed_state(endpoint.id, ObservedState.PROBING)
        try:
            snapshot = self._adapter(endpoint.adapter).probe(endpoint)
            state = transition(
                ObservedState.PROBING,
                ProbeObservation(snapshot.ready, snapshot.has_capacity),
            )
            if snapshot.models:
                self._store.replace_models(snapshot.models)
            self._store.set_observed_state(endpoint.id, state)
            return DiscoveryResult(endpoint.id.value, state, len(snapshot.models), snapshot.detail)
        except Exception as exc:
            self._store.set_observed_state(endpoint.id, ObservedState.FAILED)
            return DiscoveryResult(endpoint.id.value, ObservedState.FAILED, 0, str(exc))
