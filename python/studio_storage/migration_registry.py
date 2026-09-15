"""Deterministic registry for the storage migration dependency graph."""

from __future__ import annotations

from dataclasses import dataclass


class MigrationRegistryError(ValueError):
    """Raised when a migration registry is ambiguous or cyclic."""


@dataclass(frozen=True, slots=True)
class MigrationDomain:
    """A storage domain and the domains that must be migrated before it."""

    name: str
    dependencies: tuple[str, ...] = ()


# This is deliberately descriptive for now: existing domain runners retain ownership of
# their version tables and transaction boundaries while callers gain one inspectable graph.
STORAGE_MIGRATION_DOMAINS = (
    MigrationDomain("workspaces"),
    MigrationDomain("environments", ("workspaces",)),
    MigrationDomain("connections", ("workspaces",)),
    MigrationDomain("catalog", ("workspaces",)),
    MigrationDomain("ontology", ("catalog",)),
    MigrationDomain("quality", ("catalog",)),
    MigrationDomain("scheduler", ("workspaces",)),
    MigrationDomain("audit", ("workspaces",)),
    MigrationDomain("genai", ("catalog",)),
    MigrationDomain("ml", ("catalog",)),
)


def migration_order(domains: tuple[MigrationDomain, ...]) -> tuple[str, ...]:
    """Return a stable topological order for *domains*."""
    by_name: dict[str, MigrationDomain] = {}
    for domain in domains:
        if not domain.name or domain.name in by_name:
            raise MigrationRegistryError(f"duplicate migration domain: {domain.name!r}")
        by_name[domain.name] = domain
    for domain in domains:
        missing = sorted(set(domain.dependencies) - by_name.keys())
        if missing:
            raise MigrationRegistryError(
                f"migration domain {domain.name!r} has missing dependencies: {', '.join(missing)}"
            )

    visiting: set[str] = set()
    visited: set[str] = set()
    ordered: list[str] = []

    def visit(name: str) -> None:
        if name in visiting:
            raise MigrationRegistryError(f"migration dependency cycle includes {name!r}")
        if name in visited:
            return
        visiting.add(name)
        for dependency in sorted(by_name[name].dependencies):
            visit(dependency)
        visiting.remove(name)
        visited.add(name)
        ordered.append(name)

    for name in sorted(by_name):
        visit(name)
    return tuple(ordered)


__all__ = (
    "MigrationDomain",
    "MigrationRegistryError",
    "STORAGE_MIGRATION_DOMAINS",
    "migration_order",
)
