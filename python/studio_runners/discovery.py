"""Adapter-side runtime discovery normalized into canonical core contracts."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

from studio_core import RuntimeCatalog, RuntimeProfile


def _require_text(value: str, field_name: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")
    if "\n" in value or "\r" in value:
        raise ValueError(f"{field_name} must not contain line breaks")


@dataclass(frozen=True, order=True, slots=True)
class RuntimeDiscoveryIssue:
    """Safe, normalized discovery evidence produced at an adapter boundary."""

    code: str
    message: str

    def __post_init__(self) -> None:
        _require_text(self.code, "runtime discovery issue code")
        _require_text(self.message, "runtime discovery issue message")


@dataclass(frozen=True, slots=True)
class RuntimeDiscoveryResult:
    """One adapter's normalized profile advertisements and discovery issues."""

    adapter_id: str
    profiles: tuple[RuntimeProfile, ...] = ()
    issues: tuple[RuntimeDiscoveryIssue, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.adapter_id, "runtime discovery adapter id")
        canonical_profiles = tuple(
            sorted(self.profiles, key=lambda profile: profile.ref.profile_id)
        )
        refs = [profile.ref for profile in canonical_profiles]
        if any(ref.adapter_id != self.adapter_id for ref in refs):
            raise ValueError("discovered runtime profile must belong to the reporting adapter")
        if len(refs) != len(set(refs)):
            raise ValueError("discovered runtime profile references must be unique")
        object.__setattr__(self, "profiles", canonical_profiles)
        object.__setattr__(self, "issues", tuple(sorted(self.issues)))


class RuntimeDiscoveryAdapter(Protocol):
    """Minimal I/O SPI for discovering adapter-owned runtime profiles."""

    adapter_id: str

    def discover(self) -> RuntimeDiscoveryResult: ...


@dataclass(frozen=True, slots=True)
class RuntimeDiscoveryReport:
    """Canonical discovery output consumed by pure runtime resolution."""

    catalog: RuntimeCatalog
    issues: tuple[RuntimeDiscoveryIssue, ...] = ()


def discover_runtime_profiles(
    adapters: Iterable[RuntimeDiscoveryAdapter],
) -> RuntimeDiscoveryReport:
    """Probe adapters in stable order while containing unexpected provider failures."""
    adapter_list = tuple(adapters)
    adapter_ids = [adapter.adapter_id for adapter in adapter_list]
    for adapter_id in adapter_ids:
        _require_text(adapter_id, "runtime discovery adapter id")
    if len(adapter_ids) != len(set(adapter_ids)):
        raise ValueError("runtime discovery adapter ids must be unique")

    profiles: list[RuntimeProfile] = []
    issues: list[RuntimeDiscoveryIssue] = []
    for adapter in sorted(adapter_list, key=lambda item: item.adapter_id):
        try:
            result = adapter.discover()
        except Exception:  # noqa: BLE001 - provider exceptions must not cross this boundary
            issues.append(
                RuntimeDiscoveryIssue(
                    "runtime.discovery_failed",
                    f"runtime discovery failed for adapter {adapter.adapter_id}",
                )
            )
            continue
        if result.adapter_id != adapter.adapter_id:
            raise ValueError("runtime discovery result adapter id does not match its adapter")
        profiles.extend(result.profiles)
        issues.extend(result.issues)

    return RuntimeDiscoveryReport(RuntimeCatalog(tuple(profiles)), tuple(sorted(issues)))
