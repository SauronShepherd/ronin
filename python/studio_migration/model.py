"""Domain contracts for the Ronin Migration Studio workflow."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Literal

from studio_core.canonical_json import encode as encode_canonical_json

ObjectState = Literal["ready", "review_required", "unsupported"]


def _text(value: str, name: str) -> str:
    if not value or value != value.strip() or "\x00" in value or "\n" in value or "\r" in value:
        raise ValueError(f"{name} must be non-empty and single-line")
    return value


@dataclass(frozen=True, slots=True, order=True)
class SourceArtifact:
    name: str
    digest: str
    size_bytes: int
    media_type: str = "application/octet-stream"

    def __post_init__(self) -> None:
        _text(self.name, "artifact name")
        _text(self.digest, "artifact digest")
        _text(self.media_type, "artifact media_type")
        if self.size_bytes < 0:
            raise ValueError("artifact size_bytes must be non-negative")


@dataclass(frozen=True, slots=True, order=True)
class MigrationUnit:
    key: str
    kind: str
    name: str
    state: ObjectState
    dependencies: tuple[str, ...] = ()
    source_refs: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for value, name in (
            (self.key, "unit key"),
            (self.kind, "unit kind"),
            (self.name, "unit name"),
        ):
            _text(value, name)
        if self.state not in {"ready", "review_required", "unsupported"}:
            raise ValueError("unsupported migration unit state")
        object.__setattr__(self, "dependencies", tuple(sorted(set(self.dependencies))))
        object.__setattr__(self, "source_refs", tuple(sorted(set(self.source_refs))))


@dataclass(frozen=True, slots=True)
class SourceInventory:
    adapter_id: str
    adapter_version: str
    artifacts: tuple[SourceArtifact, ...]
    units: tuple[MigrationUnit, ...]

    def __post_init__(self) -> None:
        units = tuple(sorted(self.units, key=lambda item: item.key))
        keys = [item.key for item in units]
        if len(keys) != len(set(keys)):
            raise ValueError("inventory unit keys must be unique")
        unknown = {dep for item in units for dep in item.dependencies} - set(keys)
        if unknown:
            raise ValueError(f"inventory contains unknown dependencies: {sorted(unknown)}")
        object.__setattr__(self, "artifacts", tuple(sorted(self.artifacts)))
        object.__setattr__(self, "units", units)

    @property
    def digest(self) -> str:
        payload = {
            "adapter_id": self.adapter_id,
            "adapter_version": self.adapter_version,
            "artifacts": [
                {
                    "name": item.name,
                    "digest": item.digest,
                    "size_bytes": item.size_bytes,
                    "media_type": item.media_type,
                }
                for item in self.artifacts
            ],
            "units": [
                {
                    "key": item.key,
                    "kind": item.kind,
                    "name": item.name,
                    "state": item.state,
                    "dependencies": list(item.dependencies),
                    "source_refs": list(item.source_refs),
                    "notes": list(item.notes),
                }
                for item in self.units
            ],
        }
        return hashlib.sha256(encode_canonical_json(payload)).hexdigest()


@dataclass(frozen=True, slots=True)
class ScopeSelection:
    selected: tuple[str, ...]
    auto_included: tuple[str, ...] = ()
    reasons: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        selected = tuple(sorted(set(self.selected)))
        object.__setattr__(self, "selected", selected)
        object.__setattr__(
            self, "auto_included", tuple(sorted(set(self.auto_included) - set(selected)))
        )
        object.__setattr__(self, "reasons", tuple(sorted(self.reasons)))

    @property
    def all_units(self) -> tuple[str, ...]:
        return tuple(sorted(set(self.selected) | set(self.auto_included)))

    @property
    def digest(self) -> str:
        payload = {
            "selected": list(self.selected),
            "auto_included": list(self.auto_included),
            "reasons": [list(item) for item in self.reasons],
        }
        return hashlib.sha256(encode_canonical_json(payload)).hexdigest()
