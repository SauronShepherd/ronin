"""Persistent-catalog and lineage domain contracts for Public v1."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, TypeAlias, cast

from .canonical_json import decode as decode_canonical_json
from .canonical_json import encode as encode_canonical_json

AssetKind: TypeAlias = Literal[
    "dataset",
    "table",
    "view",
    "file",
    "stream",
    "notebook",
    "sql",
    "pipeline",
    "task",
    "model",
    "experiment",
    "feature",
    "endpoint",
    "dashboard",
    "semantic_model",
    "prompt",
    "agent",
]
LineageMode: TypeAlias = Literal["declared", "observed"]
LineageOperation: TypeAlias = Literal[
    "read",
    "write",
    "transform",
    "query",
    "train",
    "infer",
    "serve",
    "index",
]

ASSET_KINDS: frozenset[str] = frozenset(
    {
        "dataset",
        "table",
        "view",
        "file",
        "stream",
        "notebook",
        "sql",
        "pipeline",
        "task",
        "model",
        "experiment",
        "feature",
        "endpoint",
        "dashboard",
        "semantic_model",
        "prompt",
        "agent",
    }
)
_LINEAGE_OPERATIONS = frozenset(
    {"read", "write", "transform", "query", "train", "infer", "serve", "index"}
)
_SENSITIVE_PROPERTY_TERMS = (
    "password",
    "secret",
    "token",
    "credential",
    "api_key",
    "api-key",
    "access_key",
    "access-key",
    "private_key",
    "private-key",
)


def _require_text(value: str, name: str) -> str:
    if not value or value != value.strip() or "\n" in value or "\r" in value or "\x00" in value:
        raise ValueError(f"{name} must be non-empty, trimmed, and single-line")
    return value


def _canonical_pairs(
    values: tuple[tuple[str, str], ...], *, name: str, reject_sensitive: bool = False
) -> tuple[tuple[str, str], ...]:
    result: list[tuple[str, str]] = []
    seen: set[str] = set()
    for key, value in values:
        key = _require_text(key, f"{name} key")
        value = _require_text(value, f"{name} value")
        if reject_sensitive and any(term in key.casefold() for term in _SENSITIVE_PROPERTY_TERMS):
            raise ValueError(f"{name} must not contain credential-bearing keys")
        if key in seen:
            raise ValueError(f"{name} keys must be unique")
        seen.add(key)
        result.append((key, value))
    return tuple(sorted(result))


@dataclass(frozen=True, order=True, slots=True)
class AssetId:
    value: str

    def __post_init__(self) -> None:
        _require_text(self.value, "asset id")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, order=True, slots=True)
class AssetVersion:
    value: str

    def __post_init__(self) -> None:
        _require_text(self.value, "asset version")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, order=True, slots=True)
class AssetRef:
    asset_id: AssetId
    version: AssetVersion

    def to_payload(self) -> dict[str, str]:
        return {"asset_id": self.asset_id.value, "version": self.version.value}

    @classmethod
    def from_payload(cls, payload: object) -> AssetRef:
        if not isinstance(payload, Mapping) or set(payload) != {"asset_id", "version"}:
            raise ValueError("asset ref has invalid shape")
        asset_id = payload["asset_id"]
        version = payload["version"]
        if not isinstance(asset_id, str) or not isinstance(version, str):
            raise ValueError("asset ref fields must be strings")
        return cls(AssetId(asset_id), AssetVersion(version))


@dataclass(frozen=True, slots=True)
class CatalogAsset:
    """Stable governed asset identity; physical locators stay out of canonical identity."""

    id: AssetId
    kind: AssetKind
    name: str
    project_id: str | None = None
    owner_ref: str | None = None
    tags: tuple[str, ...] = ()
    classifications: tuple[str, ...] = ()
    properties: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if self.kind not in ASSET_KINDS:
            raise ValueError("unsupported catalog asset kind")
        _require_text(self.name, "asset name")
        if self.project_id is not None:
            _require_text(self.project_id, "asset project id")
        if self.owner_ref is not None:
            _require_text(self.owner_ref, "asset owner ref")
        tags = tuple(sorted(_require_text(value, "asset tag") for value in self.tags))
        if len(tags) != len(set(tags)):
            raise ValueError("asset tags must be unique")
        classifications = tuple(
            sorted(_require_text(value, "asset classification") for value in self.classifications)
        )
        if len(classifications) != len(set(classifications)):
            raise ValueError("asset classifications must be unique")
        object.__setattr__(self, "tags", tags)
        object.__setattr__(self, "classifications", classifications)
        object.__setattr__(
            self,
            "properties",
            _canonical_pairs(self.properties, name="asset properties", reject_sensitive=True),
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "id": self.id.value,
            "kind": self.kind,
            "name": self.name,
            "project_id": self.project_id,
            "owner_ref": self.owner_ref,
            "tags": list(self.tags),
            "classifications": list(self.classifications),
            "properties": dict(self.properties),
        }

    def to_json(self) -> str:
        return encode_canonical_json(self.to_payload()).decode("utf-8")

    @classmethod
    def from_payload(cls, payload: object) -> CatalogAsset:
        if not isinstance(payload, Mapping) or set(payload) != {
            "id",
            "kind",
            "name",
            "project_id",
            "owner_ref",
            "tags",
            "classifications",
            "properties",
        }:
            raise ValueError("catalog asset has invalid shape")
        asset_id = payload["id"]
        kind = payload["kind"]
        name = payload["name"]
        project_id = payload["project_id"]
        owner_ref = payload["owner_ref"]
        tags = payload["tags"]
        classifications = payload["classifications"]
        properties = payload["properties"]
        if not isinstance(asset_id, str) or not isinstance(kind, str) or not isinstance(name, str):
            raise ValueError("catalog asset id, kind, and name must be strings")
        if project_id is not None and not isinstance(project_id, str):
            raise ValueError("catalog asset project_id must be string or null")
        if owner_ref is not None and not isinstance(owner_ref, str):
            raise ValueError("catalog asset owner_ref must be string or null")
        if not isinstance(tags, list) or not all(isinstance(value, str) for value in tags):
            raise ValueError("catalog asset tags must be string array")
        if not isinstance(classifications, list) or not all(
            isinstance(value, str) for value in classifications
        ):
            raise ValueError("catalog asset classifications must be string array")
        if not isinstance(properties, Mapping) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in properties.items()
        ):
            raise ValueError("catalog asset properties must be string object")
        if kind not in ASSET_KINDS:
            raise ValueError("unsupported catalog asset kind")
        return cls(
            id=AssetId(asset_id),
            kind=cast(AssetKind, kind),
            name=name,
            project_id=cast(str | None, project_id),
            owner_ref=cast(str | None, owner_ref),
            tags=tuple(cast(list[str], tags)),
            classifications=tuple(cast(list[str], classifications)),
            properties=tuple(sorted(cast(Mapping[str, str], properties).items())),
        )

    @classmethod
    def from_json(cls, payload: str) -> CatalogAsset:
        return cls.from_payload(decode_canonical_json(payload))


@dataclass(frozen=True, slots=True)
class AssetRevision:
    """Version-addressable metadata about one committed asset state/snapshot."""

    ref: AssetRef
    schema_digest: str | None = None
    content_digest: str | None = None
    metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if self.schema_digest is not None:
            _require_text(self.schema_digest, "schema digest")
        if self.content_digest is not None:
            _require_text(self.content_digest, "content digest")
        object.__setattr__(
            self,
            "metadata",
            _canonical_pairs(self.metadata, name="asset revision metadata", reject_sensitive=True),
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "ref": self.ref.to_payload(),
            "schema_digest": self.schema_digest,
            "content_digest": self.content_digest,
            "metadata": dict(self.metadata),
        }

    def to_json(self) -> str:
        return encode_canonical_json(self.to_payload()).decode("utf-8")

    @classmethod
    def from_payload(cls, payload: object) -> AssetRevision:
        if not isinstance(payload, Mapping) or set(payload) != {
            "ref",
            "schema_digest",
            "content_digest",
            "metadata",
        }:
            raise ValueError("asset revision has invalid shape")
        schema_digest = payload["schema_digest"]
        content_digest = payload["content_digest"]
        metadata = payload["metadata"]
        if schema_digest is not None and not isinstance(schema_digest, str):
            raise ValueError("schema_digest must be string or null")
        if content_digest is not None and not isinstance(content_digest, str):
            raise ValueError("content_digest must be string or null")
        if not isinstance(metadata, Mapping) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in metadata.items()
        ):
            raise ValueError("asset revision metadata must be string object")
        return cls(
            ref=AssetRef.from_payload(payload["ref"]),
            schema_digest=cast(str | None, schema_digest),
            content_digest=cast(str | None, content_digest),
            metadata=tuple(sorted(cast(Mapping[str, str], metadata).items())),
        )

    @classmethod
    def from_json(cls, payload: str) -> AssetRevision:
        return cls.from_payload(decode_canonical_json(payload))


@dataclass(frozen=True, order=True, slots=True)
class ColumnMapping:
    target_field: str
    source_fields: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_text(self.target_field, "lineage target field")
        sources = tuple(sorted(_require_text(value, "lineage source field") for value in self.source_fields))
        if not sources:
            raise ValueError("column mapping requires at least one source field")
        if len(sources) != len(set(sources)):
            raise ValueError("column mapping source fields must be unique")
        object.__setattr__(self, "source_fields", sources)


@dataclass(frozen=True, slots=True)
class LineageEdge:
    """Committed declared/observed dependency between versioned governed assets."""

    source: AssetRef
    target: AssetRef
    operation: LineageOperation
    mode: LineageMode
    execution_ref: str | None = None
    column_mappings: tuple[ColumnMapping, ...] = ()

    def __post_init__(self) -> None:
        if self.source == self.target:
            raise ValueError("lineage edge source and target must differ")
        if self.operation not in _LINEAGE_OPERATIONS:
            raise ValueError("unsupported lineage operation")
        if self.mode not in {"declared", "observed"}:
            raise ValueError("lineage mode must be declared or observed")
        if self.execution_ref is not None:
            _require_text(self.execution_ref, "lineage execution ref")
        mappings = tuple(sorted(self.column_mappings, key=lambda item: item.target_field))
        targets = [mapping.target_field for mapping in mappings]
        if len(targets) != len(set(targets)):
            raise ValueError("lineage target fields must be unique")
        object.__setattr__(self, "column_mappings", mappings)

    def to_payload(self) -> dict[str, object]:
        return {
            "source": self.source.to_payload(),
            "target": self.target.to_payload(),
            "operation": self.operation,
            "mode": self.mode,
            "execution_ref": self.execution_ref,
            "column_mappings": [
                {
                    "target_field": mapping.target_field,
                    "source_fields": list(mapping.source_fields),
                }
                for mapping in self.column_mappings
            ],
        }

    @property
    def digest(self) -> str:
        return hashlib.sha256(encode_canonical_json(self.to_payload())).hexdigest()

    def to_json(self) -> str:
        return encode_canonical_json(self.to_payload()).decode("utf-8")

    @classmethod
    def from_payload(cls, payload: object) -> LineageEdge:
        if not isinstance(payload, Mapping) or set(payload) != {
            "source",
            "target",
            "operation",
            "mode",
            "execution_ref",
            "column_mappings",
        }:
            raise ValueError("lineage edge has invalid shape")
        operation = payload["operation"]
        mode = payload["mode"]
        execution_ref = payload["execution_ref"]
        mappings = payload["column_mappings"]
        if not isinstance(operation, str) or operation not in _LINEAGE_OPERATIONS:
            raise ValueError("unsupported lineage operation")
        if not isinstance(mode, str) or mode not in {"declared", "observed"}:
            raise ValueError("unsupported lineage mode")
        if execution_ref is not None and not isinstance(execution_ref, str):
            raise ValueError("lineage execution_ref must be string or null")
        if not isinstance(mappings, list):
            raise ValueError("lineage column_mappings must be an array")
        parsed_mappings: list[ColumnMapping] = []
        for mapping in mappings:
            if not isinstance(mapping, Mapping) or set(mapping) != {"target_field", "source_fields"}:
                raise ValueError("column mapping has invalid shape")
            target_field = mapping["target_field"]
            source_fields = mapping["source_fields"]
            if not isinstance(target_field, str) or not isinstance(source_fields, list) or not all(
                isinstance(value, str) for value in source_fields
            ):
                raise ValueError("column mapping has invalid field types")
            parsed_mappings.append(ColumnMapping(target_field, tuple(source_fields)))
        return cls(
            source=AssetRef.from_payload(payload["source"]),
            target=AssetRef.from_payload(payload["target"]),
            operation=cast(LineageOperation, operation),
            mode=cast(LineageMode, mode),
            execution_ref=cast(str | None, execution_ref),
            column_mappings=tuple(parsed_mappings),
        )

    @classmethod
    def from_json(cls, payload: str) -> LineageEdge:
        return cls.from_payload(decode_canonical_json(payload))
