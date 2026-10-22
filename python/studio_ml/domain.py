"""Immutable domain contracts for Machine Learning Studio labs and pipelines."""
# ruff: noqa: E501

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Literal, TypeAlias, cast

from studio_core.canonical_json import decode as decode_canonical_json
from studio_core.canonical_json import encode as encode_canonical_json
from studio_core.catalog import AssetRef

from .catalog import validate_catalog_version

LabTask: TypeAlias = Literal["classification", "regression", "clustering"]
NodeKind: TypeAlias = Literal[
    "profile", "quality_gate", "prepare", "train", "evaluate", "select", "register"
] | str
LAB_SCHEMA = "ronin.ml-lab/v1"
PIPELINE_SCHEMA = "ronin.ml-pipeline-ir/v1"
PIPELINE_SCHEMA_V2 = "ronin.ml-pipeline-ir/v2"
PIPELINE_SCHEMA_V3 = "ronin.ml-pipeline-ir/v3"
MAX_PIPELINE_NODES = 24
MAX_PIPELINE_EDGES_V3 = 48
MAX_PIPELINE_CONFIG_BYTES_V3 = 16 * 1024
MAX_PIPELINE_BYTES_V3 = 64 * 1024
FEATURE_SCHEMA = "ronin.ml-feature/v1"
MAX_DOMAIN_TEXT = 256
MAX_FEATURE_SPECS = 256


def _is_finite_number(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(float(value))
    except OverflowError:
        return False


def _text(value: object, name: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > MAX_DOMAIN_TEXT
        or any(c in value for c in "\r\n\x00")
    ):
        raise ValueError(f"{name} must be non-empty, trimmed, and single-line")
    return value


def _split_output_reference(reference: str) -> tuple[str, str]:
    if not isinstance(reference, str) or "." not in reference:
        raise ValueError("pipeline output references must use node_id.output_port")
    node_id, output_port = reference.rsplit(".", 1)
    _text(node_id, "pipeline output node id")
    _text(output_port, "pipeline output port")
    return node_id, output_port


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
        if self.schema != FEATURE_SCHEMA:
            raise ValueError("invalid feature definition schema or version")
        validate_catalog_version(self.version, "feature definition")
        if (
            not self.features
            or len(self.features) > MAX_FEATURE_SPECS
            or len({item.column for item in self.features}) != len(self.features)
        ):
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
        expected = {
            "schema", "id", "name", "project_id", "dataset", "features", "transform", "version"
        }
        if not isinstance(payload, Mapping) or set(payload) != expected:
            raise ValueError("feature definition has invalid shape")
        raw_features = payload["features"]
        if not isinstance(raw_features, list) or len(raw_features) > MAX_FEATURE_SPECS:
            raise ValueError("feature definition features must be an array")
        features: list[FeatureSpec] = []
        for item in raw_features:
            if (
                not isinstance(item, Mapping)
                or set(item) != {"column", "role"}
                or not isinstance(item["column"], str)
                or not isinstance(item["role"], str)
            ):
                raise ValueError("feature definition feature has invalid shape")
            features.append(FeatureSpec(cast(str, item["column"]), cast(str, item["role"])))
        if not all(isinstance(payload[name], str) for name in ("schema", "id", "name", "project_id", "transform")):
            raise ValueError("feature definition text fields must be strings")
        if not isinstance(payload["version"], int) or isinstance(payload["version"], bool):
            raise ValueError("feature definition version must be an integer")
        return cls(
            cast(str, payload["id"]),
            cast(str, payload["name"]),
            cast(str, payload["project_id"]),
            AssetRef.from_payload(payload["dataset"]),
            tuple(features),
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
        if (
            not self.features
            or len(self.features) > MAX_FEATURE_SPECS
            or len({item.column for item in self.features}) != len(self.features)
        ):
            raise ValueError("lab features must be non-empty and unique")
        if self.target is not None and self.target in {item.column for item in self.features}:
            raise ValueError("target must not also be a feature")
        if not isinstance(self.seed, int) or isinstance(self.seed, bool) or self.seed < 0:
            raise ValueError("seed must be a non-negative integer")
        if (
            not _is_finite_number(self.test_fraction)
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
            or len(payload["features"]) > MAX_FEATURE_SPECS
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
    inputs: tuple[tuple[str, tuple[str, ...]], ...] = ()
    stage_version: int = 1

    def __post_init__(self) -> None:
        _text(self.id, "pipeline node id")
        if not isinstance(self.kind, str) or (
            self.kind not in {
                "profile",
                "quality_gate",
                "prepare",
                "train",
                "evaluate",
                "select",
                "register",
            }
            and re.fullmatch(
                r"[a-z0-9][a-z0-9.-]{0,127}/[a-z][a-z0-9_-]{0,63}", self.kind
            )
            is None
        ):
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
        if not isinstance(self.stage_version, int) or isinstance(self.stage_version, bool):
            raise ValueError("pipeline stage version must be an integer")
        normalized_inputs: list[tuple[str, tuple[str, ...]]] = []
        for port, references in self.inputs:
            _text(port, "pipeline input port")
            if (
                not isinstance(references, tuple)
                or not references
                or any(not isinstance(reference, str) for reference in references)
            ):
                raise ValueError("pipeline input references must be non-empty string tuples")
            if len(set(references)) != len(references):
                raise ValueError("pipeline input references must be unique per port")
            for reference in references:
                _split_output_reference(reference)
            normalized_inputs.append((port, tuple(sorted(references))))
        if len({port for port, _ in normalized_inputs}) != len(normalized_inputs):
            raise ValueError("pipeline input ports must be unique")
        object.__setattr__(self, "inputs", tuple(sorted(normalized_inputs)))

    def to_payload(
        self, *, include_config: bool = False, schema: str = PIPELINE_SCHEMA
    ) -> dict[str, object]:
        if schema == PIPELINE_SCHEMA_V3:
            return {
                "id": self.id,
                "kind": self.kind,
                "stage_version": self.stage_version,
                "config": _thaw_json(self.config),
                "inputs": {port: list(refs) for port, refs in self.inputs},
            }
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
        if not isinstance(payload, Mapping):
            raise ValueError("pipeline node has invalid shape")
        if set(payload) == {"id", "kind", "stage_version", "config", "inputs"}:
            inputs = payload["inputs"]
            if (
                not isinstance(payload["id"], str)
                or not isinstance(payload["kind"], str)
                or not isinstance(payload["stage_version"], int)
                or isinstance(payload["stage_version"], bool)
                or not isinstance(payload["config"], Mapping)
                or not isinstance(inputs, Mapping)
                or any(
                    not isinstance(port, str)
                    or not isinstance(refs, list)
                    or not all(isinstance(reference, str) for reference in refs)
                    for port, refs in inputs.items()
                )
            ):
                raise ValueError("pipeline v3 node fields have invalid types")
            return cls(
                payload["id"],
                cast(NodeKind, payload["kind"]),
                config=payload["config"],
                inputs=tuple((port, tuple(refs)) for port, refs in sorted(inputs.items())),
                stage_version=payload["stage_version"],
            )
        if set(payload) not in (
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
        if (
            not isinstance(self.schema, str)
            or self.schema not in {PIPELINE_SCHEMA, PIPELINE_SCHEMA_V2, PIPELINE_SCHEMA_V3}
            or not self.nodes
        ):
            raise ValueError("invalid or empty pipeline schema")
        if len(self.nodes) > MAX_PIPELINE_NODES:
            raise ValueError(f"pipeline cannot contain more than {MAX_PIPELINE_NODES} nodes")
        if self.schema != PIPELINE_SCHEMA_V3 and any(
            node.kind not in {
                "profile",
                "quality_gate",
                "prepare",
                "train",
                "evaluate",
                "select",
                "register",
            }
            for node in self.nodes
        ):
            raise ValueError("plugin pipeline stages require PipelineIR v3")
        if self.schema != PIPELINE_SCHEMA_V3 and any(
            node.inputs or node.stage_version != 1 for node in self.nodes
        ):
            raise ValueError("typed pipeline inputs and stage versions require PipelineIR v3")
        if self.schema == PIPELINE_SCHEMA and any(node.config for node in self.nodes):
            raise ValueError("PipelineIR v1 nodes cannot contain configuration")
        if self.schema == PIPELINE_SCHEMA_V2 and any(
            node.kind not in {"prepare", "train", "select", "register"} and node.config
            for node in self.nodes
        ):
            raise ValueError(
                "PipelineIR v2 only supports prepare, train, select, and register node configuration"
            )
        if self.schema == PIPELINE_SCHEMA_V3 and (
            len(self.parameters) > 6
            or any(
                not isinstance(key, str) or not isinstance(value, str)
                for key, value in self.parameters
            )
            or len({key for key, _ in self.parameters}) != len(self.parameters)
        ):
            raise ValueError("PipelineIR v3 parameters must be at most six unique string pairs")
        if self.schema == PIPELINE_SCHEMA_V3:
            self._validate_v3()
        ids = {node.id for node in self.nodes}
        dependencies = {node.id: self.dependency_ids(node) for node in self.nodes}
        if len(ids) != len(self.nodes) or any(
            dep not in ids for deps in dependencies.values() for dep in deps
        ):
            raise ValueError("pipeline node ids and dependencies must resolve")
        pending = {node_id: set(deps) for node_id, deps in dependencies.items()}
        resolved: set[str] = set()
        while pending:
            ready = {node_id for node_id, deps in pending.items() if deps <= resolved}
            if not ready:
                raise ValueError("pipeline graph must be acyclic")
            resolved.update(ready)
            for node_id in ready:
                pending.pop(node_id)
        if self.schema == PIPELINE_SCHEMA_V3:
            object.__setattr__(self, "nodes", self.execution_order())

    def to_payload(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "nodes": [
                node.to_payload(
                    include_config=self.schema == PIPELINE_SCHEMA_V2, schema=self.schema
                )
                for node in self.nodes
            ],
            "parameters": dict(self.parameters),
        }

    def dependency_ids(self, node: PipelineNode) -> tuple[str, ...]:
        if self.schema != PIPELINE_SCHEMA_V3:
            return node.depends_on
        return tuple(
            sorted(
                {
                    _split_output_reference(reference)[0]
                    for _, references in node.inputs
                    for reference in references
                }
            )
        )

    def _validate_v3(self) -> None:
        from .pipeline_stages import BUILTIN_STAGE_REGISTRY, validate_stage_configuration

        if any(node.depends_on for node in self.nodes):
            raise ValueError("PipelineIR v3 uses typed input references, not depends_on")
        by_id = {node.id: node for node in self.nodes}
        if len(by_id) != len(self.nodes):
            raise ValueError("pipeline node ids must be unique")
        config_bytes = 0
        edge_count = 0
        outgoing: dict[str, int] = {node.id: 0 for node in self.nodes}
        for node in self.nodes:
            if len(node.id) > 256:
                raise ValueError("PipelineIR v3 node ids cannot exceed 256 characters")
            definition = BUILTIN_STAGE_REGISTRY.get(node.kind)
            if definition is None:
                if not re.fullmatch(
                    r"[a-z0-9][a-z0-9.-]{0,127}/[a-z][a-z0-9_-]{0,63}", node.kind
                ):
                    raise ValueError("PipelineIR v3 plugin stage must use a namespaced id")
                if node.stage_version < 1 or len(node.config) > 32 or len(node.inputs) > 16:
                    raise ValueError("PipelineIR v3 plugin stage exceeds structural limits")
            else:
                validate_stage_configuration(node.kind, node.stage_version, node.config)
            if node.kind == "register" and any(
                len(cast(str, node.config[key])) > 256 for key in ("model_id", "version")
            ):
                raise ValueError("PipelineIR v3 register identifiers cannot exceed 256 characters")
            config_bytes += len(encode_canonical_json(_thaw_json(node.config)))
            supplied_ports = dict(node.inputs)
            if definition is not None and set(supplied_ports) != set(definition.inputs):
                raise ValueError(f"PipelineIR v3 {node.kind} inputs do not match its stage contract")
            if definition is None and any(
                not re.fullmatch(r"[a-z][a-z0-9_.-]{0,63}", port)
                or not references
                or len(references) > MAX_PIPELINE_NODES
                for port, references in supplied_ports.items()
            ):
                raise ValueError("PipelineIR v3 plugin stage has invalid input ports")
            for port, references in supplied_ports.items():
                contract = definition.inputs.get(port) if definition is not None else None
                if contract is not None and not contract.minimum <= len(references) <= contract.maximum:
                    raise ValueError(f"PipelineIR v3 input {port!r} has invalid cardinality")
                edge_count += len(references)
                for reference in references:
                    source_id, output_name = _split_output_reference(reference)
                    source = by_id.get(source_id)
                    if source is None:
                        raise ValueError("PipelineIR v3 input references an unknown node")
                    source_definition = BUILTIN_STAGE_REGISTRY.get(source.kind)
                    if output_name != "out" or (
                        contract is not None
                        and source_definition is not None
                        and source_definition.output_type != contract.value_type
                    ):
                        raise ValueError(
                            "PipelineIR v3 input reference has an incompatible output type"
                        )
                    outgoing[source_id] += 1
                    if outgoing[source_id] > 8:
                        raise ValueError("PipelineIR v3 node fan-out exceeds 8")
        if edge_count > MAX_PIPELINE_EDGES_V3:
            raise ValueError(
                f"PipelineIR v3 cannot contain more than {MAX_PIPELINE_EDGES_V3} edges"
            )
        if config_bytes > MAX_PIPELINE_CONFIG_BYTES_V3:
            raise ValueError("PipelineIR v3 stage configuration exceeds the byte limit")
        profiles = [node for node in self.nodes if node.kind == "profile"]
        gates = [node for node in self.nodes if node.kind == "quality_gate"]
        selectors = [node for node in self.nodes if node.kind == "select"]
        registrations = [node for node in self.nodes if node.kind == "register"]
        if len(profiles) != 1 or len(gates) != 1 or len(selectors) != 1 or len(registrations) > 1:
            raise ValueError(
                "PipelineIR v3 requires one profile, quality_gate, select and at most one register"
            )
        if registrations and self.dependency_ids(registrations[0]) != (selectors[0].id,):
            raise ValueError("PipelineIR v3 register must be terminal and depend on select")
        ancestors: set[str] = set()
        pending = [selectors[0].id]
        while pending:
            current = pending.pop()
            for dependency in self.dependency_ids(by_id[current]):
                if dependency not in ancestors:
                    ancestors.add(dependency)
                    pending.append(dependency)
        expected = set(by_id) - {node.id for node in registrations}
        if ancestors | {selectors[0].id} != expected:
            raise ValueError("PipelineIR v3 contains nodes that do not contribute to selection")
        size = len(encode_canonical_json(self.to_payload()))
        if size > MAX_PIPELINE_BYTES_V3:
            raise ValueError("PipelineIR v3 payload exceeds the byte limit")

    def execution_order(self) -> tuple[PipelineNode, ...]:
        """Return a stable topological order for this immutable graph."""

        remaining = {node.id: node for node in self.nodes}
        resolved: set[str] = set()
        ordered: list[PipelineNode] = []
        while remaining:
            ready = sorted(
                node_id
                for node_id, node in remaining.items()
                if set(self.dependency_ids(node)) <= resolved
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
        schema = payload["schema"]
        if not isinstance(schema, str):
            raise ValueError("pipeline IR schema must be a string")
        parsed = []
        for item in nodes:
            if not isinstance(item, Mapping):
                raise ValueError("pipeline IR node must be an object")
            parsed.append(PipelineNode.from_payload(item))
        if not all(
            isinstance(key, str) and isinstance(value, str) for key, value in parameters.items()
        ):
            raise ValueError("pipeline IR parameters must be string pairs")
        if schema == PIPELINE_SCHEMA and any(
            "config" in item for item in nodes if isinstance(item, Mapping)
        ):
            raise ValueError("PipelineIR v1 nodes cannot contain configuration")
        if schema in {PIPELINE_SCHEMA_V2, PIPELINE_SCHEMA_V3} and any(
            not isinstance(item, Mapping) or "config" not in item for item in nodes
        ):
            raise ValueError("PipelineIR v2/v3 nodes require explicit config objects")
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
    "PIPELINE_SCHEMA",
    "PIPELINE_SCHEMA_V2",
    "PIPELINE_SCHEMA_V3",
]
