"""Immutable domain contracts for Machine Learning Studio labs and pipelines."""
# ruff: noqa: E501

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Literal, TypeAlias, cast

from studio_core.canonical_json import decode as decode_canonical_json
from studio_core.canonical_json import encode as encode_canonical_json
from studio_core.catalog import AssetRef

LabTask: TypeAlias = Literal["classification", "regression", "clustering"]
NodeKind: TypeAlias = Literal[
    "profile", "quality_gate", "prepare", "train", "evaluate", "select", "register"
]
LAB_SCHEMA = "ronin.ml-lab/v1"
PIPELINE_SCHEMA = "ronin.ml-pipeline-ir/v1"
PIPELINE_SCHEMA_V2 = "ronin.ml-pipeline-ir/v2"
MAX_PIPELINE_NODES = 20
FEATURE_SCHEMA = "ronin.ml-feature/v1"


def _text(value: object, name: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or any(c in value for c in "\r\n\x00")
    ):
        raise ValueError(f"{name} must be non-empty, trimmed, and single-line")
    return value


def _freeze_json(value: object) -> object:
    """Copy a canonical JSON value into recursively immutable containers."""

    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze_json(child) for key, child in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(child) for child in value)
    return value


def _thaw_json(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _thaw_json(child) for key, child in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(child) for child in value]
    return value


def _validate_json_object_keys(value: object) -> None:
    """Reject non-string mapping keys before Python's JSON encoder coerces them."""
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise ValueError("pipeline node config object keys must be strings")
        for child in value.values():
            _validate_json_object_keys(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _validate_json_object_keys(child)


@dataclass(frozen=True, slots=True)
class FeatureSpec:
    column: str
    role: str = "auto"

    def __post_init__(self) -> None:
        _text(self.column, "feature column")
        if self.role not in {"auto", "numeric", "categorical", "text", "datetime", "ignored"}:
            raise ValueError("unsupported feature role")

    def to_payload(self) -> dict[str, str]:
        return {"column": self.column, "role": self.role}


@dataclass(frozen=True, slots=True)
class FeatureDefinition:
    """Versioned, reusable feature binding to a governed dataset snapshot."""

    id: str
    name: str
    project_id: str
    dataset: AssetRef
    features: tuple[FeatureSpec, ...]
    transform: str = "identity"
    version: int = 1
    schema: str = FEATURE_SCHEMA

    def __post_init__(self) -> None:
        _text(self.id, "feature definition id")
        _text(self.name, "feature definition name")
        _text(self.project_id, "feature definition project")
        _text(self.transform, "feature transform")
        if (
            self.schema != FEATURE_SCHEMA
            or not isinstance(self.version, int)
            or isinstance(self.version, bool)
            or self.version < 1
        ):
            raise ValueError("invalid feature definition schema or version")
        if not self.features or len({item.column for item in self.features}) != len(self.features):
            raise ValueError("feature definition columns must be non-empty and unique")

    def to_payload(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "id": self.id,
            "name": self.name,
            "project_id": self.project_id,
            "dataset": self.dataset.to_payload(),
            "features": [item.to_payload() for item in self.features],
            "transform": self.transform,
            "version": self.version,
        }

    def to_json(self) -> str:
        return encode_canonical_json(self.to_payload()).decode("utf-8")

    @classmethod
    def from_payload(cls, payload: object) -> FeatureDefinition:
        if (
            not isinstance(payload, Mapping)
            or set(payload)
            != {"schema", "id", "name", "project_id", "dataset", "features", "transform", "version"}
            or not isinstance(payload["features"], list)
        ):
            raise ValueError("feature definition has invalid shape")
        return cls(
            cast(str, payload["id"]),
            cast(str, payload["name"]),
            cast(str, payload["project_id"]),
            AssetRef.from_payload(payload["dataset"]),
            tuple(
                FeatureSpec(cast(str, item["column"]), cast(str, item["role"]))
                for item in payload["features"]
            ),
            cast(str, payload["transform"]),
            cast(int, payload["version"]),
            cast(str, payload["schema"]),
        )

    @classmethod
    def from_json(cls, payload: str) -> FeatureDefinition:
        return cls.from_payload(decode_canonical_json(payload))


@dataclass(frozen=True, slots=True)
class Lab:
    id: str
    name: str
    project_id: str
    dataset: AssetRef
    target: str | None
    task: LabTask
    features: tuple[FeatureSpec, ...]
    backend_id: str = "local.sklearn"
    seed: int = 17
    test_fraction: float = 0.2
    schema: str = LAB_SCHEMA
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _text(self.id, "lab id")
        _text(self.name, "lab name")
        _text(self.project_id, "project id")
        _text(self.backend_id, "backend id")
        if self.schema != LAB_SCHEMA:
            raise ValueError(f"unsupported lab schema: {self.schema}")
        if self.task not in {"classification", "regression", "clustering"}:
            raise ValueError("unsupported lab task")
        if self.task == "clustering" and self.target is not None:
            raise ValueError("clustering labs must not define a target")
        if self.task != "clustering" and not self.target:
            raise ValueError("supervised labs require a target")
        if self.target is not None:
            _text(self.target, "target")
        if not self.features or len({item.column for item in self.features}) != len(self.features):
            raise ValueError("lab features must be non-empty and unique")
        if self.target is not None and self.target in {item.column for item in self.features}:
            raise ValueError("target must not also be a feature")
        if not isinstance(self.seed, int) or isinstance(self.seed, bool) or self.seed < 0:
            raise ValueError("seed must be a non-negative integer")
        if (
            not isinstance(self.test_fraction, (int, float))
            or isinstance(self.test_fraction, bool)
            or not math.isfinite(float(self.test_fraction))
            or not 0 < self.test_fraction < 1
        ):
            raise ValueError("invalid seed or test fraction")
        known_fields = {
            "schema",
            "id",
            "name",
            "project_id",
            "dataset",
            "target",
            "task",
            "features",
            "backend_id",
            "seed",
            "test_fraction",
        }
        if not isinstance(self.metadata, Mapping) or any(
            not isinstance(key, str) or key in known_fields for key in self.metadata
        ):
            raise ValueError("lab metadata must contain only unknown string fields")
        metadata = decode_canonical_json(encode_canonical_json(_thaw_json(self.metadata)))
        if not isinstance(metadata, Mapping):
            raise ValueError("lab metadata must be a JSON object")
        object.__setattr__(self, "metadata", _freeze_json(metadata))

    def to_payload(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "id": self.id,
            "name": self.name,
            "project_id": self.project_id,
            "dataset": self.dataset.to_payload(),
            "target": self.target,
            "task": self.task,
            "features": [item.to_payload() for item in self.features],
            "backend_id": self.backend_id,
            "seed": self.seed,
            "test_fraction": self.test_fraction,
            **{key: _thaw_json(value) for key, value in self.metadata.items()},
        }

    def to_json(self) -> str:
        return encode_canonical_json(self.to_payload()).decode("utf-8")

    @property
    def digest(self) -> str:
        """Return the SHA-256 identity of this canonical lab definition."""

        return hashlib.sha256(self.to_json().encode("utf-8")).hexdigest()

    @classmethod
    def from_payload(cls, payload: object) -> Lab:
        if not isinstance(payload, Mapping):
            raise ValueError("lab must be an object")
        expected = {
            "schema",
            "id",
            "name",
            "project_id",
            "dataset",
            "target",
            "task",
            "features",
            "backend_id",
            "seed",
            "test_fraction",
        }
        if (
            not expected.issubset(payload)
            or not isinstance(payload["features"], list)
            or any(
                not isinstance(item, Mapping) or set(item) != {"column", "role"}
                for item in payload["features"]
            )
        ):
            raise ValueError("lab has invalid shape")
        return cls(
            id=cast(str, payload["id"]),
            name=cast(str, payload["name"]),
            project_id=cast(str, payload["project_id"]),
            dataset=AssetRef.from_payload(payload["dataset"]),
            target=cast(str | None, payload["target"]),
            task=cast(LabTask, payload["task"]),
            features=tuple(
                FeatureSpec(cast(str, item["column"]), cast(str, item["role"]))
                for item in cast(list[Mapping[str, object]], payload["features"])
            ),
            backend_id=cast(str, payload["backend_id"]),
            seed=cast(int, payload["seed"]),
            test_fraction=cast(float, payload["test_fraction"]),
            schema=cast(str, payload["schema"]),
            metadata={key: value for key, value in payload.items() if key not in expected},
        )

    @classmethod
    def from_json(cls, payload: str) -> Lab:
        return cls.from_payload(decode_canonical_json(payload))


@dataclass(frozen=True, slots=True)
class PipelineNode:
    id: str
    kind: NodeKind
    depends_on: tuple[str, ...] = ()
    config: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _text(self.id, "pipeline node id")
        if self.kind not in {
            "profile",
            "quality_gate",
            "prepare",
            "train",
            "evaluate",
            "select",
            "register",
        }:
            raise ValueError("unsupported pipeline node kind")
        if self.id in self.depends_on or len(set(self.depends_on)) != len(self.depends_on):
            raise ValueError("pipeline node dependencies must be unique and not self-referential")
        frozen = _freeze_json(self.config)
        if not isinstance(frozen, Mapping):
            raise ValueError("pipeline node config must be an object")
        _validate_json_object_keys(frozen)
        # Round-trip through canonical JSON to reject non-JSON values and non-string keys.
        canonical = decode_canonical_json(encode_canonical_json(_thaw_json(frozen)))
        if not isinstance(canonical, Mapping):
            raise ValueError("pipeline node config must be an object")
        object.__setattr__(self, "config", _freeze_json(canonical))

    def to_payload(self, *, include_config: bool = False) -> dict[str, object]:
        payload: dict[str, object] = {
            "id": self.id,
            "kind": self.kind,
            "depends_on": list(self.depends_on),
        }
        if include_config:
            payload["config"] = _thaw_json(self.config)
        return payload

    @classmethod
    def from_payload(cls, payload: object) -> PipelineNode:
        if not isinstance(payload, Mapping) or set(payload) not in (
            {"id", "kind", "depends_on"},
            {"id", "kind", "depends_on", "config"},
        ):
            raise ValueError("pipeline node has invalid shape")
        if (
            not isinstance(payload["id"], str)
            or not isinstance(payload["kind"], str)
            or not isinstance(payload["depends_on"], list)
        ):
            raise ValueError("pipeline node fields have invalid types")
        if not all(isinstance(item, str) for item in payload["depends_on"]):
            raise ValueError("pipeline node dependencies must be strings")
        config = payload.get("config", {})
        if not isinstance(config, Mapping):
            raise ValueError("pipeline node config must be an object")
        return cls(
            payload["id"], cast(NodeKind, payload["kind"]), tuple(payload["depends_on"]), config
        )


@dataclass(frozen=True, slots=True)
class PipelineIR:
    nodes: tuple[PipelineNode, ...]
    parameters: tuple[tuple[str, str], ...] = ()
    schema: str = PIPELINE_SCHEMA

    def __post_init__(self) -> None:
        if self.schema not in {PIPELINE_SCHEMA, PIPELINE_SCHEMA_V2} or not self.nodes:
            raise ValueError("invalid or empty pipeline schema")
        if len(self.nodes) > MAX_PIPELINE_NODES:
            raise ValueError(f"pipeline cannot contain more than {MAX_PIPELINE_NODES} nodes")
        if self.schema == PIPELINE_SCHEMA and any(node.config for node in self.nodes):
            raise ValueError("PipelineIR v1 nodes cannot contain configuration")
        if self.schema == PIPELINE_SCHEMA_V2 and any(
            node.kind not in {"prepare", "train", "select"} and node.config for node in self.nodes
        ):
            raise ValueError(
                "PipelineIR v2 only supports prepare, train, and select node configuration"
            )
        ids = {node.id for node in self.nodes}
        if len(ids) != len(self.nodes) or any(
            dep not in ids for node in self.nodes for dep in node.depends_on
        ):
            raise ValueError("pipeline node ids and dependencies must resolve")
        pending = {node.id: set(node.depends_on) for node in self.nodes}
        resolved: set[str] = set()
        while pending:
            ready = {node_id for node_id, deps in pending.items() if deps <= resolved}
            if not ready:
                raise ValueError("pipeline graph must be acyclic")
            resolved.update(ready)
            for node_id in ready:
                pending.pop(node_id)

    def to_payload(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "nodes": [
                node.to_payload(include_config=self.schema == PIPELINE_SCHEMA_V2)
                for node in self.nodes
            ],
            "parameters": dict(self.parameters),
        }

    def execution_order(self) -> tuple[PipelineNode, ...]:
        """Return a stable topological order for this immutable graph."""

        remaining = {node.id: node for node in self.nodes}
        resolved: set[str] = set()
        ordered: list[PipelineNode] = []
        while remaining:
            ready = sorted(
                node_id for node_id, node in remaining.items() if set(node.depends_on) <= resolved
            )
            if not ready:
                # Construction rejects cycles; retain a defensive guard for mutated inputs.
                raise ValueError("pipeline graph must be acyclic")
            for node_id in ready:
                ordered.append(remaining.pop(node_id))
                resolved.add(node_id)
        return tuple(ordered)

    def to_json(self) -> str:
        return encode_canonical_json(self.to_payload()).decode("utf-8")

    @property
    def digest(self) -> str:
        """Return the SHA-256 identity of this canonical pipeline definition."""

        return hashlib.sha256(self.to_json().encode("utf-8")).hexdigest()

    @classmethod
    def from_payload(cls, payload: object) -> PipelineIR:
        if not isinstance(payload, Mapping) or set(payload) != {"schema", "nodes", "parameters"}:
            raise ValueError("pipeline IR has invalid shape")
        nodes = payload["nodes"]
        parameters = payload["parameters"]
        if not isinstance(nodes, list) or not isinstance(parameters, Mapping):
            raise ValueError("pipeline IR nodes/parameters have invalid types")
        parsed = []
        for item in nodes:
            if not isinstance(item, Mapping):
                raise ValueError("pipeline IR node must be an object")
            parsed.append(PipelineNode.from_payload(item))
        if not all(
            isinstance(key, str) and isinstance(value, str) for key, value in parameters.items()
        ):
            raise ValueError("pipeline IR parameters must be string pairs")
        schema = cast(str, payload["schema"])
        if schema == PIPELINE_SCHEMA and any(
            "config" in item for item in nodes if isinstance(item, Mapping)
        ):
            raise ValueError("PipelineIR v1 nodes cannot contain configuration")
        if schema == PIPELINE_SCHEMA_V2 and any(
            not isinstance(item, Mapping) or "config" not in item for item in nodes
        ):
            raise ValueError("PipelineIR v2 nodes require explicit config objects")
        return cls(tuple(parsed), tuple(sorted(parameters.items())), schema)

    @classmethod
    def from_json(cls, payload: str) -> PipelineIR:
        return cls.from_payload(decode_canonical_json(payload))


__all__ = [
    "FEATURE_SCHEMA",
    "FeatureDefinition",
    "FeatureSpec",
    "Lab",
    "LabTask",
    "NodeKind",
    "PipelineIR",
    "PipelineNode",
]
