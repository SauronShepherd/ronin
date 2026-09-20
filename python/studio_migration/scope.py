"""Deterministic scope selection and dependency closure."""
from __future__ import annotations

from collections.abc import Iterable

from .model import ScopeSelection, SourceInventory


def select_scope(inventory: SourceInventory, requested: Iterable[str]) -> ScopeSelection:
    """Select units and include every transitive dependency with an audit reason."""
    known = {unit.key: unit for unit in inventory.units}
    initial = tuple(sorted(set(requested)))
    missing = set(initial) - set(known)
    if missing:
        raise ValueError(f"scope references unknown migration units: {sorted(missing)}")
    auto: set[str] = set()
    reasons: dict[str, str] = {}
    visiting: set[str] = set()

    def visit(key: str, parent: str | None = None) -> None:
        if key in visiting:
            raise ValueError(f"migration dependency cycle includes {key}")
        if parent is not None and key not in initial:
            auto.add(key)
            reasons.setdefault(key, f"required by {parent}")
        visiting.add(key)
        for dependency in known[key].dependencies:
            visit(dependency, key)
        visiting.remove(key)

    for key in initial:
        visit(key)
    return ScopeSelection(initial, tuple(auto), tuple(reasons.items()))


def select_all(inventory: SourceInventory) -> ScopeSelection:
    return select_scope(inventory, (unit.key for unit in inventory.units))


__all__ = ("select_all", "select_scope")
