"""Deterministic identifiers for pure Ronin domain objects."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from hashlib import sha256
from typing import Literal, TypeAlias

InstanceBoundary: TypeAlias = Literal["authoring", "import"]


@dataclass(frozen=True, order=True, slots=True)
class InstanceAnchor:
    """Stable authoring/import provenance used to derive a node instance key."""

    boundary: InstanceBoundary
    reference: str

    def __post_init__(self) -> None:
        if self.boundary not in {"authoring", "import"}:
            raise ValueError("instance anchor boundary must be authoring or import")
        if not self.reference or self.reference.strip() != self.reference:
            raise ValueError("instance anchor reference must be non-empty and trimmed")
        if "\n" in self.reference or "\r" in self.reference:
            raise ValueError("instance anchor reference must be single-line")

    def instance_key(self) -> str:
        payload = f"ronin-instance-v1\0{self.boundary}\0{self.reference}".encode()
        return sha256(payload).hexdigest()


def allocate_instance_keys(anchors: Sequence[InstanceAnchor]) -> tuple[str, ...]:
    """Derive stable keys from explicit anchors, rejecting ambiguous duplicates."""
    if len(set(anchors)) != len(anchors):
        raise ValueError("instance anchors must be unique within an allocation batch")
    return tuple(anchor.instance_key() for anchor in anchors)


@dataclass(frozen=True, order=True, slots=True)
class NodeId:
    """Stable node identifier derived from semantic content plus an instance key."""

    value: str

    @classmethod
    def derive(cls, semantic_payload: str, instance_key: str) -> NodeId:
        if not instance_key:
            raise ValueError("instance_key must be non-empty")
        payload = f"ronin-node-v1\0{instance_key}\0{semantic_payload}".encode()
        return cls(sha256(payload).hexdigest())

    def __str__(self) -> str:
        return self.value
