"""Provider-neutral engine discovery with fail-closed transport boundaries."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from .contracts import EngineCapabilities, EngineHandshake


class DiscoveryClient(Protocol):
    """Minimal transport port; concrete HTTP/provider clients stay outside the contract."""

    def get_json(self, path: str) -> object: ...


@dataclass(frozen=True, slots=True)
class DiscoveredEngine:
    handshake: EngineHandshake
    engines: tuple[str, ...]
    cluster_state: str

    def __post_init__(self) -> None:
        if not self.engines or any(
            not isinstance(value, str) or not value.strip() for value in self.engines
        ):
            raise ValueError("engine registry must contain non-empty names")
        if len(set(self.engines)) != len(self.engines):
            raise ValueError("engine registry names must be unique")
        if not isinstance(self.cluster_state, str) or not self.cluster_state.strip():
            raise ValueError("cluster state must be non-empty text")


def _mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"discovery {name} response must be an object")
    return value


def discover_engine(
    client: DiscoveryClient,
    *,
    provider_id: str,
    health_path: str = "/health",
    registry_path: str = "/engines",
    cluster_path: str = "/cluster",
) -> DiscoveredEngine:
    """Collect bounded discovery metadata without treating omission as false."""

    health = _mapping(client.get_json(health_path), "health")
    registry = _mapping(client.get_json(registry_path), "registry")
    cluster = _mapping(client.get_json(cluster_path), "cluster")

    healthy = health.get("healthy")
    version = health.get("version")
    if not isinstance(healthy, bool) or not isinstance(version, str) or not version.strip():
        raise ValueError("discovery health must declare boolean healthy and non-empty version")

    raw_capabilities = health.get("capabilities", {})
    capabilities = _mapping(raw_capabilities, "capabilities")
    capability_items: list[tuple[str, bool | None]] = []
    for name, value in capabilities.items():
        if not isinstance(name, str) or not name.strip():
            raise ValueError("discovery capability names must be non-empty strings")
        if value is not None and not isinstance(value, bool):
            raise ValueError("discovery capability values must be boolean or null")
        capability_items.append((name, value))

    raw_engines = registry.get("engines")
    if not isinstance(raw_engines, list) or not raw_engines:
        raise ValueError("discovery registry must contain a non-empty engines array")
    engines = tuple(raw_engines)
    if not all(isinstance(value, str) and value.strip() for value in engines):
        raise ValueError("discovery engine names must be non-empty strings")
    state = cluster.get("state")
    if not isinstance(state, str) or not state.strip():
        raise ValueError("discovery cluster must declare a non-empty state")

    cluster_id = cluster.get("id")
    if cluster_id is not None and not isinstance(cluster_id, str):
        raise ValueError("discovery cluster id must be text when present")
    handshake = EngineHandshake(
        provider_id,
        version,
        EngineCapabilities(tuple(capability_items)),
        healthy,
        cluster_id=cluster_id,
    )
    return DiscoveredEngine(handshake, engines, state)


__all__ = ("DiscoveredEngine", "DiscoveryClient", "discover_engine")
