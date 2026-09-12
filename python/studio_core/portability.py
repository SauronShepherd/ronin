"""Canonical Ronin Bundle and migration-report contracts for Public v1."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, TypeAlias, cast

from .canonical_json import decode as decode_canonical_json
from .canonical_json import encode as encode_canonical_json

MigrationStatus: TypeAlias = Literal[
    "exact",
    "translated",
    "partial",
    "passthrough",
    "unsupported",
    "manual_decision",
]
BindingKind: TypeAlias = Literal[
    "connection",
    "secret",
    "runtime",
    "identity",
    "notification",
    "model_provider",
    "storage",
    "endpoint",
]

MIGRATION_STATUSES: frozenset[str] = frozenset(
    {"exact", "translated", "partial", "passthrough", "unsupported", "manual_decision"}
)
BINDING_KINDS: frozenset[str] = frozenset(
    {
        "connection",
        "secret",
        "runtime",
        "identity",
        "notification",
        "model_provider",
        "storage",
        "endpoint",
    }
)
RONIN_BUNDLE_SCHEMA_VERSION = 1


def _require_text(value: str, name: str) -> str:
    if not value or value != value.strip() or "\n" in value or "\r" in value or "\x00" in value:
        raise ValueError(f"{name} must be non-empty, trimmed, and single-line")
    return value


def _require_safe_path(value: str) -> str:
    value = _require_text(value, "bundle path")
    if value.startswith("/") or "\\" in value:
        raise ValueError("bundle path must be relative and use forward slashes")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("bundle path contains unsafe path components")
    return value


def _reject_credential_material(value: str, name: str) -> str:
    value = _require_text(value, name)
    folded = value.casefold()
    if folded.startswith("bearer ") or "-----begin " in folded or "password=" in folded:
        raise ValueError(f"{name} must not contain credential material")
    return value


@dataclass(frozen=True, order=True, slots=True)
class BundleEntry:
    path: str
    media_type: str
    digest_algorithm: str
    digest: str
    size_bytes: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", _require_safe_path(self.path))
        _require_text(self.media_type, "bundle entry media_type")
        _require_text(self.digest_algorithm, "bundle entry digest_algorithm")
        _require_text(self.digest, "bundle entry digest")
        if self.size_bytes < 0:
            raise ValueError("bundle entry size_bytes must be non-negative")

    def to_payload(self) -> dict[str, object]:
        return {
            "path": self.path,
            "media_type": self.media_type,
            "digest_algorithm": self.digest_algorithm,
            "digest": self.digest,
            "size_bytes": self.size_bytes,
        }

    @classmethod
    def from_payload(cls, payload: object) -> BundleEntry:
        if not isinstance(payload, Mapping) or set(payload) != {
            "path",
            "media_type",
            "digest_algorithm",
            "digest",
            "size_bytes",
        }:
            raise ValueError("bundle entry has invalid shape")
        path = payload["path"]
        media_type = payload["media_type"]
        algorithm = payload["digest_algorithm"]
        digest = payload["digest"]
        size = payload["size_bytes"]
        if not all(isinstance(value, str) for value in (path, media_type, algorithm, digest)):
            raise ValueError("bundle entry string fields are invalid")
        if not isinstance(size, int) or isinstance(size, bool):
            raise ValueError("bundle entry size_bytes must be integer")
        return cls(
            cast(str, path),
            cast(str, media_type),
            cast(str, algorithm),
            cast(str, digest),
            size,
        )


@dataclass(frozen=True, order=True, slots=True)
class BindingRequest:
    kind: BindingKind
    source_ref: str
    required: bool = True
    suggested_target_ref: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in BINDING_KINDS:
            raise ValueError("unsupported binding kind")
        object.__setattr__(
            self,
            "source_ref",
            _reject_credential_material(self.source_ref, "binding source_ref"),
        )
        if self.suggested_target_ref is not None:
            object.__setattr__(
                self,
                "suggested_target_ref",
                _reject_credential_material(
                    self.suggested_target_ref, "binding suggested_target_ref"
                ),
            )

    def to_payload(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "source_ref": self.source_ref,
            "required": self.required,
            "suggested_target_ref": self.suggested_target_ref,
        }

    @classmethod
    def from_payload(cls, payload: object) -> BindingRequest:
        if not isinstance(payload, Mapping) or set(payload) != {
            "kind",
            "source_ref",
            "required",
            "suggested_target_ref",
        }:
            raise ValueError("binding request has invalid shape")
        kind = payload["kind"]
        source_ref = payload["source_ref"]
        required = payload["required"]
        suggestion = payload["suggested_target_ref"]
        if not isinstance(kind, str) or kind not in BINDING_KINDS:
            raise ValueError("unsupported binding kind")
        if not isinstance(source_ref, str) or not isinstance(required, bool):
            raise ValueError("binding request has invalid field types")
        if suggestion is not None and not isinstance(suggestion, str):
            raise ValueError("binding suggestion must be string or null")
        return cls(cast(BindingKind, kind), source_ref, required, cast(str | None, suggestion))


@dataclass(frozen=True, order=True, slots=True)
class MigrationObjectReport:
    source_type: str
    source_id: str
    status: MigrationStatus
    target_refs: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    binding_requests: tuple[BindingRequest, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.source_type, "migration source type")
        _require_text(self.source_id, "migration source id")
        if self.status not in MIGRATION_STATUSES:
            raise ValueError("unsupported migration status")
        targets = tuple(sorted(_require_text(value, "migration target ref") for value in self.target_refs))
        if len(targets) != len(set(targets)):
            raise ValueError("migration target refs must be unique")
        notes = tuple(_reject_credential_material(value, "migration note") for value in self.notes)
        bindings = tuple(sorted(self.binding_requests))
        object.__setattr__(self, "target_refs", targets)
        object.__setattr__(self, "notes", notes)
        object.__setattr__(self, "binding_requests", bindings)
        if self.status in {"unsupported", "manual_decision"} and not notes:
            raise ValueError("unsupported/manual_decision migration objects require explanatory notes")

    @property
    def source_key(self) -> tuple[str, str]:
        return (self.source_type, self.source_id)

    def to_payload(self) -> dict[str, object]:
        return {
            "source_type": self.source_type,
            "source_id": self.source_id,
            "status": self.status,
            "target_refs": list(self.target_refs),
            "notes": list(self.notes),
            "binding_requests": [item.to_payload() for item in self.binding_requests],
        }

    @classmethod
    def from_payload(cls, payload: object) -> MigrationObjectReport:
        if not isinstance(payload, Mapping) or set(payload) != {
            "source_type",
            "source_id",
            "status",
            "target_refs",
            "notes",
            "binding_requests",
        }:
            raise ValueError("migration object report has invalid shape")
        source_type = payload["source_type"]
        source_id = payload["source_id"]
        status = payload["status"]
        target_refs = payload["target_refs"]
        notes = payload["notes"]
        bindings = payload["binding_requests"]
        if not isinstance(source_type, str) or not isinstance(source_id, str):
            raise ValueError("migration source fields must be strings")
        if not isinstance(status, str) or status not in MIGRATION_STATUSES:
            raise ValueError("unsupported migration status")
        if not isinstance(target_refs, list) or not all(isinstance(value, str) for value in target_refs):
            raise ValueError("migration target_refs must be string array")
        if not isinstance(notes, list) or not all(isinstance(value, str) for value in notes):
            raise ValueError("migration notes must be string array")
        if not isinstance(bindings, list):
            raise ValueError("migration binding_requests must be array")
        return cls(
            source_type,
            source_id,
            cast(MigrationStatus, status),
            tuple(target_refs),
            tuple(notes),
            tuple(BindingRequest.from_payload(item) for item in bindings),
        )


@dataclass(frozen=True, slots=True)
class MigrationReport:
    source_platform: str
    source_version: str
    importer_version: str
    objects: tuple[MigrationObjectReport, ...]

    def __post_init__(self) -> None:
        _require_text(self.source_platform, "migration source platform")
        _require_text(self.source_version, "migration source version")
        _require_text(self.importer_version, "migration importer version")
        objects = tuple(sorted(self.objects, key=lambda item: item.source_key))
        keys = [item.source_key for item in objects]
        if len(keys) != len(set(keys)):
            raise ValueError("each source migration object must appear exactly once")
        object.__setattr__(self, "objects", objects)

    @property
    def unresolved_bindings(self) -> tuple[BindingRequest, ...]:
        requests = [request for item in self.objects for request in item.binding_requests]
        return tuple(sorted(set(requests)))

    @property
    def requires_manual_decision(self) -> bool:
        return any(item.status == "manual_decision" for item in self.objects) or any(
            request.required for request in self.unresolved_bindings
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "source_platform": self.source_platform,
            "source_version": self.source_version,
            "importer_version": self.importer_version,
            "objects": [item.to_payload() for item in self.objects],
        }

    @property
    def digest(self) -> str:
        return hashlib.sha256(encode_canonical_json(self.to_payload())).hexdigest()

    def to_json(self) -> str:
        return encode_canonical_json(self.to_payload()).decode("utf-8")

    @classmethod
    def from_payload(cls, payload: object) -> MigrationReport:
        if not isinstance(payload, Mapping) or set(payload) != {
            "source_platform",
            "source_version",
            "importer_version",
            "objects",
        }:
            raise ValueError("migration report has invalid shape")
        source_platform = payload["source_platform"]
        source_version = payload["source_version"]
        importer_version = payload["importer_version"]
        objects = payload["objects"]
        if not all(isinstance(value, str) for value in (source_platform, source_version, importer_version)):
            raise ValueError("migration report identity/version fields must be strings")
        if not isinstance(objects, list):
            raise ValueError("migration report objects must be array")
        return cls(
            cast(str, source_platform),
            cast(str, source_version),
            cast(str, importer_version),
            tuple(MigrationObjectReport.from_payload(item) for item in objects),
        )

    @classmethod
    def from_json(cls, payload: str) -> MigrationReport:
        return cls.from_payload(decode_canonical_json(payload))


@dataclass(frozen=True, slots=True)
class RoninBundleManifest:
    """Content-addressed manifest; entries contain no secret values or host-local paths."""

    entries: tuple[BundleEntry, ...]
    migration_reports: tuple[MigrationReport, ...] = ()
    schema_version: int = RONIN_BUNDLE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != RONIN_BUNDLE_SCHEMA_VERSION:
            raise ValueError("unsupported Ronin Bundle schema version")
        entries = tuple(sorted(self.entries))
        paths = [entry.path for entry in entries]
        if len(paths) != len(set(paths)):
            raise ValueError("Ronin Bundle entry paths must be unique")
        reports = tuple(sorted(self.migration_reports, key=lambda item: (item.source_platform, item.digest)))
        object.__setattr__(self, "entries", entries)
        object.__setattr__(self, "migration_reports", reports)

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "entries": [entry.to_payload() for entry in self.entries],
            "migration_reports": [report.to_payload() for report in self.migration_reports],
        }

    @property
    def digest(self) -> str:
        return hashlib.sha256(encode_canonical_json(self.to_payload())).hexdigest()

    def to_json(self) -> str:
        return encode_canonical_json(self.to_payload()).decode("utf-8")

    @classmethod
    def from_payload(cls, payload: object) -> RoninBundleManifest:
        if not isinstance(payload, Mapping) or set(payload) != {
            "schema_version",
            "entries",
            "migration_reports",
        }:
            raise ValueError("Ronin Bundle manifest has invalid shape")
        version = payload["schema_version"]
        entries = payload["entries"]
        reports = payload["migration_reports"]
        if not isinstance(version, int) or isinstance(version, bool):
            raise ValueError("Ronin Bundle schema_version must be integer")
        if not isinstance(entries, list) or not isinstance(reports, list):
            raise ValueError("Ronin Bundle entries/reports must be arrays")
        return cls(
            tuple(BundleEntry.from_payload(item) for item in entries),
            tuple(MigrationReport.from_payload(item) for item in reports),
            version,
        )

    @classmethod
    def from_json(cls, payload: str) -> RoninBundleManifest:
        return cls.from_payload(decode_canonical_json(payload))
