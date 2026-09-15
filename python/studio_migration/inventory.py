"""Fail-closed migration inventory kernel.

The kernel deliberately does not pretend to translate vendor semantics. It
classifies every discovered object exactly once and emits portable binding
requests for references that must be resolved by an operator.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast

from studio_core.portability import BindingRequest, MigrationObjectReport, MigrationReport


@dataclass(frozen=True, slots=True)
class SourceObject:
    """One source-platform object discovered from a JSON document."""

    object_type: str
    object_id: str
    status: str = "unsupported"
    target_refs: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    bindings: tuple[BindingRequest, ...] = ()

    def report(self) -> MigrationObjectReport:
        return MigrationObjectReport(
            self.object_type,
            self.object_id,
            self.status,  # type: ignore[arg-type]
            self.target_refs,
            self.notes or (("No executable Ronin target mapping is registered",) if self.status == "unsupported" else ()),
            self.bindings,
        )


class MigrationInventory:
    """Build a complete deterministic report from normalized source objects."""

    def __init__(self, source_platform: str, source_version: str, importer_version: str) -> None:
        self.source_platform = source_platform
        self.source_version = source_version
        self.importer_version = importer_version
        self._objects: list[SourceObject] = []

    def add(self, obj: SourceObject) -> None:
        if any(existing.object_type == obj.object_type and existing.object_id == obj.object_id for existing in self._objects):
            raise ValueError("source object must be classified exactly once")
        self._objects.append(obj)

    def report(self) -> MigrationReport:
        return MigrationReport(
            self.source_platform,
            self.source_version,
            self.importer_version,
            tuple(obj.report() for obj in self._objects),
        )


def inventory_json_document(
    document: str | bytes,
    *,
    source_platform: str,
    source_version: str,
    importer_version: str,
) -> MigrationReport:
    """Inventory a normalized JSON object list and classify every object.

    Accepted shape is ``{"objects": [{"type": ..., "id": ..., ...}]}``.
    Unknown fields are ignored for discovery, but malformed identity fields,
    duplicate identities, and invalid binding declarations fail closed.
    """

    try:
        payload: Any = json.loads(document)
    except (TypeError, ValueError) as exc:
        raise ValueError("migration source document is not valid JSON") from exc
    if not isinstance(payload, Mapping) or not isinstance(payload.get("objects"), Sequence) or isinstance(payload["objects"], (str, bytes)):
        raise ValueError("migration source document must contain an objects array")
    inventory = MigrationInventory(source_platform, source_version, importer_version)
    for item in payload["objects"]:
        if not isinstance(item, Mapping) or not isinstance(item.get("type"), str) or not isinstance(item.get("id"), str):
            raise ValueError("every migration object requires string type and id")
        bindings: list[BindingRequest] = []
        raw_bindings = item.get("bindings", [])
        if not isinstance(raw_bindings, Sequence) or isinstance(raw_bindings, (str, bytes)):
            raise ValueError("object bindings must be an array")
        for raw in raw_bindings:
            if not isinstance(raw, Mapping):
                raise ValueError("binding declarations must be objects")
            bindings.append(
                BindingRequest(
                    cast(Any, raw.get("kind")),
                    str(raw.get("source_ref")),
                    bool(raw.get("required", True)),
                )
            )
        status = item.get("status", "unsupported")
        if not isinstance(status, str):
            raise ValueError("migration status must be a string")
        notes = item.get("notes", ())
        if not isinstance(notes, Sequence) or isinstance(notes, (str, bytes)) or not all(isinstance(note, str) for note in notes):
            raise ValueError("migration notes must be a string array")
        inventory.add(SourceObject(str(item["type"]), str(item["id"]), status, (), tuple(notes), tuple(bindings)))
    return inventory.report()
