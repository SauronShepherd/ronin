"""Deterministic identifiers for pure Ronin domain objects."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256


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
