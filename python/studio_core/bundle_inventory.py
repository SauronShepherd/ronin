"""Canonical semantic inventory carried inside a Ronin Bundle."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from .canonical_json import decode as decode_canonical_json
from .canonical_json import encode as encode_canonical_json
from .portability import BindingRequest

BUNDLE_INVENTORY_SCHEMA = "ronin.bundle.inventory/v1"
BUNDLE_INVENTORY_PATH = "ronin-inventory.json"


def _require_text(value: str, name: str) -> str:
    if not value or value != value.strip() or "\n" in value or "\r" in value or "\x00" in value:
        raise ValueError(f"{name} must be non-empty, trimmed, and single-line")
    return value


def _require_safe_path(value: str) -> str:
    value = _require_text(value, "bundle inventory path")
    if value.startswith("/") or "\\" in value:
        raise ValueError("bundle inventory path must be relative and use forward slashes")
    if any(part in {"", ".", ".."} for part in value.split("/")):
        raise ValueError("bundle inventory path contains unsafe components")
    if value == BUNDLE_INVENTORY_PATH:
        raise ValueError("bundle object path must not reuse the inventory path")
    return value


@dataclass(frozen=True, slots=True)
class BundleInventoryObject:
    """One portable logical object and its payload location inside the bundle."""

    kind: str
    logical_ref: str
    path: str
    dependencies: tuple[str, ...] = ()
    binding_requests: tuple[BindingRequest, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.kind, "bundle inventory object kind")
        _require_text(self.logical_ref, "bundle inventory logical_ref")
        object.__setattr__(self, "path", _require_safe_path(self.path))
        dependencies = tuple(sorted(_require_text(item, "bundle dependency") for item in self.dependencies))
        if len(dependencies) != len(set(dependencies)):
            raise ValueError("bundle inventory dependencies must be unique")
        bindings = tuple(sorted(self.binding_requests))
        object.__setattr__(self, "dependencies", dependencies)
        object.__setattr__(self, "binding_requests", bindings)

    @property
    def key(self) -> tuple[str, str]:
        return (self.kind, self.logical_ref)

    def to_payload(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "logical_ref": self.logical_ref,
            "path": self.path,
            "dependencies": list(self.dependencies),
            "binding_requests": [request.to_payload() for request in self.binding_requests],
        }

    @classmethod
    def from_payload(cls, payload: object) -> BundleInventoryObject:
        if not isinstance(payload, Mapping) or set(payload) != {
            "kind",
            "logical_ref",
            "path",
            "dependencies",
            "binding_requests",
        }:
            raise ValueError("bundle inventory object has invalid shape")
        kind = payload["kind"]
        logical_ref = payload["logical_ref"]
        path = payload["path"]
        dependencies = payload["dependencies"]
        bindings = payload["binding_requests"]
        if not all(isinstance(value, str) for value in (kind, logical_ref, path)):
            raise ValueError("bundle inventory object identity fields must be strings")
        if not isinstance(dependencies, list) or not all(
            isinstance(value, str) for value in dependencies
        ):
            raise ValueError("bundle inventory dependencies must be a string array")
        if not isinstance(bindings, list):
            raise ValueError("bundle inventory binding_requests must be an array")
        return cls(
            cast(str, kind),
            cast(str, logical_ref),
            cast(str, path),
            tuple(dependencies),
            tuple(BindingRequest.from_payload(item) for item in bindings),
        )


@dataclass(frozen=True, slots=True)
class BundleInventory:
    """Deterministic semantic index for portable objects in one Ronin Bundle."""

    objects: tuple[BundleInventoryObject, ...]
    schema: str = BUNDLE_INVENTORY_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != BUNDLE_INVENTORY_SCHEMA:
            raise ValueError("unsupported Ronin Bundle inventory schema")
        objects = tuple(sorted(self.objects, key=lambda item: item.key))
        keys = [item.key for item in objects]
        paths = [item.path for item in objects]
        if len(keys) != len(set(keys)):
            raise ValueError("bundle inventory object identities must be unique")
        if len(paths) != len(set(paths)):
            raise ValueError("bundle inventory object paths must be unique")
        known_refs = {item.logical_ref for item in objects}
        for item in objects:
            unknown = set(item.dependencies) - known_refs
            if unknown:
                raise ValueError(
                    f"bundle inventory object has unknown dependencies: {sorted(unknown)}"
                )
        object.__setattr__(self, "objects", objects)

    @property
    def unresolved_bindings(self) -> tuple[BindingRequest, ...]:
        requests = [request for item in self.objects for request in item.binding_requests]
        return tuple(sorted(set(requests)))

    def to_payload(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "objects": [item.to_payload() for item in self.objects],
        }

    @property
    def digest(self) -> str:
        return hashlib.sha256(encode_canonical_json(self.to_payload())).hexdigest()

    def to_json(self) -> str:
        return encode_canonical_json(self.to_payload()).decode("utf-8")

    @classmethod
    def from_payload(cls, payload: object) -> BundleInventory:
        if not isinstance(payload, Mapping) or set(payload) != {"schema", "objects"}:
            raise ValueError("bundle inventory has invalid shape")
        schema = payload["schema"]
        objects = payload["objects"]
        if not isinstance(schema, str):
            raise ValueError("bundle inventory schema must be string")
        if not isinstance(objects, list):
            raise ValueError("bundle inventory objects must be an array")
        return cls(
            tuple(BundleInventoryObject.from_payload(item) for item in objects),
            schema,
        )

    @classmethod
    def from_json(cls, payload: str) -> BundleInventory:
        return cls.from_payload(decode_canonical_json(payload))


__all__ = (
    "BUNDLE_INVENTORY_PATH",
    "BUNDLE_INVENTORY_SCHEMA",
    "BundleInventory",
    "BundleInventoryObject",
)
