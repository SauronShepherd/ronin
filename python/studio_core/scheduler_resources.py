"""Provider-neutral scheduler resource-pool contracts."""

from __future__ import annotations

from dataclasses import dataclass

from .canonical_json import decode as decode_canonical_json
from .canonical_json import encode as encode_canonical_json


def _require_pool_name(value: str) -> str:
    if (
        not value
        or value != value.strip()
        or "\n" in value
        or "\r" in value
        or "\x00" in value
    ):
        raise ValueError("resource pool name must be non-empty, trimmed, and single-line")
    if len(value) > 256:
        raise ValueError("resource pool name must be at most 256 characters")
    return value


@dataclass(frozen=True, order=True, slots=True)
class ResourcePoolDefinition:
    """Workspace-local capacity for one portable task-policy pool name."""

    name: str
    capacity: int

    def __post_init__(self) -> None:
        _require_pool_name(self.name)
        if self.capacity < 1:
            raise ValueError("resource pool capacity must be positive")

    def to_payload(self) -> dict[str, object]:
        return {"name": self.name, "capacity": self.capacity}

    def to_json(self) -> str:
        return encode_canonical_json(self.to_payload()).decode("utf-8")

    @classmethod
    def from_payload(cls, payload: object) -> ResourcePoolDefinition:
        if not isinstance(payload, dict) or set(payload) != {"name", "capacity"}:
            raise ValueError("resource pool definition has invalid shape")
        name = payload["name"]
        capacity = payload["capacity"]
        if not isinstance(name, str):
            raise ValueError("resource pool name must be string")
        if not isinstance(capacity, int) or isinstance(capacity, bool):
            raise ValueError("resource pool capacity must be integer")
        return cls(name, capacity)

    @classmethod
    def from_json(cls, payload: str) -> ResourcePoolDefinition:
        return cls.from_payload(decode_canonical_json(payload))


__all__ = ("ResourcePoolDefinition",)
