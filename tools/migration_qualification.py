"""Fail-closed checks for Ronin's forward-only migration inventory."""

from __future__ import annotations

import re
from pathlib import Path

_MIGRATION_NAME = re.compile(
    r"^(?:\d{3}(?:_[a-z0-9][a-z0-9_-]*)?|[a-z0-9]+(?:_[a-z0-9]+)*_\d{3}(?:_[a-z0-9][a-z0-9_-]*)?)\.sql$"
)


class MigrationQualificationError(ValueError):
    pass


def discover_migrations(directory: Path) -> tuple[Path, ...]:
    paths = tuple(sorted(directory.glob("*.sql"), key=lambda item: item.name))
    if not paths:
        raise MigrationQualificationError("migration directory is empty")
    return paths


def qualify_migrations(directory: Path) -> tuple[str, ...]:
    paths = discover_migrations(directory)
    names: list[str] = []
    for path in paths:
        if not _MIGRATION_NAME.fullmatch(path.name):
            raise MigrationQualificationError(f"invalid forward migration name: {path.name}")
        lowered = path.name.casefold()
        if any(term in lowered for term in ("rollback", "down", "revert")):
            raise MigrationQualificationError(f"reverse migration is not allowed: {path.name}")
        text = path.read_text(encoding="utf-8")
        if not text.strip():
            raise MigrationQualificationError(f"migration is empty: {path.name}")
        names.append(path.name)
    if len(set(names)) != len(names):
        raise MigrationQualificationError("duplicate migration names")
    return tuple(names)


__all__ = ("MigrationQualificationError", "discover_migrations", "qualify_migrations")
