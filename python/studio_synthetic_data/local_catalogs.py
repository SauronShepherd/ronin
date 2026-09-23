"""Offline catalog profiles for Synthetic Data Studio."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LocalCatalogProfile:
    provider_id: str
    display_name: str
    namespace_levels: tuple[str, ...]
    capabilities: tuple[str, ...]
    mode: str = "local"

    def to_payload(self) -> dict[str, object]:
        return {
            "provider_id": self.provider_id,
            "display_name": self.display_name,
            "mode": self.mode,
            "namespace_levels": list(self.namespace_levels),
            "capabilities": list(self.capabilities),
        }


LOCAL_CATALOG_PROFILES = (
    LocalCatalogProfile(
        "ronin-sqlite",
        "Ronin Local Catalog",
        ("workspace", "namespace", "asset"),
        ("assets", "revisions", "lineage", "search"),
    ),
    LocalCatalogProfile(
        "unity-catalog-local",
        "Unity Catalog (local profile)",
        ("catalog", "schema", "table"),
        ("assets", "revisions", "lineage", "search", "three-level-namespace"),
    ),
    LocalCatalogProfile(
        "polaris-local",
        "Apache Polaris (local profile)",
        ("catalog", "namespace", "table"),
        ("assets", "revisions", "lineage", "search", "namespace-branching"),
    ),
)


def list_local_catalog_profiles() -> tuple[LocalCatalogProfile, ...]:
    return LOCAL_CATALOG_PROFILES


def resolve_local_identifier(provider_id: str, identifier: str) -> dict[str, str]:
    """Resolve a local catalog identifier into its provider namespace."""
    profile = next(
        (item for item in LOCAL_CATALOG_PROFILES if item.provider_id == provider_id), None
    )
    if profile is None:
        raise ValueError(f"unknown local catalog provider: {provider_id}")
    parts = tuple(part for part in identifier.split(".") if part)
    if len(parts) != len(profile.namespace_levels):
        expected = ".".join(profile.namespace_levels)
        raise ValueError(f"{provider_id} identifiers must follow {expected}")
    return dict(zip(profile.namespace_levels, parts, strict=True))


__all__ = ["LocalCatalogProfile", "list_local_catalog_profiles", "resolve_local_identifier"]
