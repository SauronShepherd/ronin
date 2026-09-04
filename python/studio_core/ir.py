"""Immutable, canonical and provider-neutral intermediate representation."""

from __future__ import annotations

import hashlib
import heapq
import json
import math
from bisect import bisect_left
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal, TypeAlias, cast

from .ids import NodeId

Scalar: TypeAlias = None | bool | int | float | str
PortKind: TypeAlias = Literal["batch", "stream"]
Ownership: TypeAlias = Literal["GRAPH", "USER", "RECONCILED"]
OriginView: TypeAlias = Literal["graph", "notebook", "imported", "system"]


@dataclass(frozen=True, slots=True)
class FrozenList:
    items: tuple[FrozenValue, ...]


@dataclass(frozen=True, slots=True)
class FrozenMap:
    items: tuple[tuple[str, FrozenValue], ...]


FrozenValue: TypeAlias = Scalar | FrozenList | FrozenMap


def freeze_value(value: object) -> FrozenValue:
    """Convert JSON-compatible values to deterministic, hashable domain values."""
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("IR float values must be finite")
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Mapping):
        items: list[tuple[str, FrozenValue]] = []
        for key, child in value.items():
            if not isinstance(key, str):
                raise TypeError("IR mapping keys must be strings")
            items.append((key, freeze_value(child)))
        return FrozenMap(tuple(sorted(items, key=lambda item: item[0])))
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return FrozenList(tuple(freeze_value(child) for child in value))
    raise TypeError(f"unsupported IR value type: {type(value).__name__}")


def thaw_value(value: FrozenValue) -> object:
    if isinstance(value, FrozenMap):
        return {key: thaw_value(child) for key, child in value.items}
    if isinstance(value, FrozenList):
        return [thaw_value(child) for child in value.items]
    return value


def _frozen_comparison_key(value: FrozenValue) -> object:
    if value is None:
        return ("null",)
    if isinstance(value, bool):
        return ("bool", value)
    if isinstance(value, int):
        return ("int", value)
    if isinstance(value, float):
        return ("float", value.hex())
    if isinstance(value, str):
        return ("str", value)
    if isinstance(value, FrozenList):
        return ("list", tuple(_frozen_comparison_key(child) for child in value.items))
    return (
        "map",
        tuple((key, _frozen_comparison_key(child)) for key, child in value.items),
    )


@dataclass(frozen=True, order=True, slots=True)
class SchemaRef:
    name: str
    version: str | None = None


@dataclass(frozen=True, order=True, slots=True)
class Port:
    name: str
    kind: PortKind = "batch"
    schema: SchemaRef | None = None


@dataclass(frozen=True, order=True, slots=True)
class OperatorRef:
    name: str
    version: int = 1

    def __post_init__(self) -> None:
        if self.version < 1:
            raise ValueError("operator version must be >= 1")


@dataclass(frozen=True, order=True, slots=True)
class Origin:
    view: OriginView
    reference: str | None = None


DEFAULT_ORIGIN = Origin("system")


def _port_sort_key(port: Port) -> tuple[str, str, str, str]:
    if port.schema is None:
        return (port.name, port.kind, "", "")
    return (port.name, port.kind, port.schema.name, port.schema.version or "")


@dataclass(frozen=True, slots=True, eq=False)
class Node:
    id: NodeId
    instance_key: str
    operator: OperatorRef
    params: tuple[tuple[str, FrozenValue], ...] = ()
    inputs: tuple[Port, ...] = ()
    outputs: tuple[Port, ...] = ()
    origin: Origin = DEFAULT_ORIGIN
    ownership: Ownership = "GRAPH"
    label: str | None = field(default=None, compare=False, hash=False)

    def __post_init__(self) -> None:
        if not self.instance_key:
            raise ValueError("instance_key must be non-empty")
        canonical_params = tuple(sorted(self.params, key=lambda item: item[0]))
        names = [name for name, _ in canonical_params]
        if len(names) != len(set(names)):
            raise ValueError("node parameter names must be unique")
        canonical_inputs = tuple(sorted(self.inputs, key=_port_sort_key))
        canonical_outputs = tuple(sorted(self.outputs, key=_port_sort_key))
        object.__setattr__(self, "params", canonical_params)
        object.__setattr__(self, "inputs", canonical_inputs)
        object.__setattr__(self, "outputs", canonical_outputs)
        expected = NodeId.derive(
            _node_semantic_payload(
                self.operator,
                canonical_params,
                canonical_inputs,
                canonical_outputs,
            ),
            self.instance_key,
        )
        if self.id != expected:
            raise ValueError("node id does not match semantic content and instance_key")

    def _comparison_key(self) -> object:
        return (
            self.id,
            self.instance_key,
            self.operator,
            tuple((key, _frozen_comparison_key(value)) for key, value in self.params),
            self.inputs,
            self.outputs,
            self.origin,
            self.ownership,
        )

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Node) and self._comparison_key() == other._comparison_key()

    def __hash__(self) -> int:
        return hash(self._comparison_key())

    @classmethod
    def create(
        cls,
        *,
        operator: OperatorRef,
        instance_key: str,
        params: Mapping[str, object] | None = None,
        inputs: Sequence[Port] = (),
        outputs: Sequence[Port] = (),
        origin: Origin = DEFAULT_ORIGIN,
        ownership: Ownership = "GRAPH",
        label: str | None = None,
    ) -> Node:
        frozen_params = tuple(
            sorted(
                ((key, freeze_value(value)) for key, value in (params or {}).items()),
                key=lambda item: item[0],
            )
        )
        canonical_inputs = tuple(sorted(inputs, key=_port_sort_key))
        canonical_outputs = tuple(sorted(outputs, key=_port_sort_key))
        semantic = _node_semantic_payload(
            operator,
            frozen_params,
            canonical_inputs,
            canonical_outputs,
        )
        return cls(
            id=NodeId.derive(semantic, instance_key),
            instance_key=instance_key,
            operator=operator,
            params=frozen_params,
            inputs=canonical_inputs,
            outputs=canonical_outputs,
            origin=origin,
            ownership=ownership,
            label=label,
        )

    def param(self, name: str) -> FrozenValue | None:
        names = tuple(key for key, _ in self.params)
        index = bisect_left(names, name)
        if index < len(self.params) and self.params[index][0] == name:
            return self.params[index][1]
        return None


@dataclass(frozen=True, order=True, slots=True)
class Edge:
    source: NodeId
    source_port: str
    target: NodeId
    target_port: str


@dataclass(frozen=True, order=True, slots=True)
class PipelineConfig:
    name: str = "main"


@dataclass(frozen=True, slots=True)
class Pipeline:
    nodes: tuple[Node, ...] = ()
    edges: tuple[Edge, ...] = ()
    config: PipelineConfig = PipelineConfig()

    def __post_init__(self) -> None:
        canonical_nodes = tuple(sorted(self.nodes, key=lambda node: node.id.value))
        canonical_edges = tuple(sorted(self.edges))
        object.__setattr__(self, "nodes", canonical_nodes)
        object.__setattr__(self, "edges", canonical_edges)
        _validate_pipeline(canonical_nodes, canonical_edges)

    def to_data(self) -> dict[str, object]:
        return {
            "config": {"name": self.config.name},
            "nodes": [_node_to_data(node) for node in self.nodes],
            "edges": [_edge_to_data(edge) for edge in self.edges],
        }

    def to_json(self) -> str:
        return _canonical_json(self.to_data())

    def content_digest(self) -> str:
        """Return a deterministic SHA-256 digest of the canonical pipeline document."""
        return hashlib.sha256(self.to_json().encode()).hexdigest()

    @classmethod
    def from_data(cls, data: Mapping[str, object]) -> Pipeline:
        config_data = _require_mapping(data.get("config"), "config")
        nodes_data = _require_sequence(data.get("nodes"), "nodes")
        edges_data = _require_sequence(data.get("edges"), "edges")
        return cls(
            nodes=tuple(_node_from_data(_require_mapping(item, "node")) for item in nodes_data),
            edges=tuple(_edge_from_data(_require_mapping(item, "edge")) for item in edges_data),
            config=PipelineConfig(name=_require_str(config_data.get("name"), "config.name")),
        )

    @classmethod
    def from_json(cls, payload: str) -> Pipeline:
        data = json.loads(payload)
        return cls.from_data(_require_mapping(data, "pipeline"))


def _validate_pipeline(nodes: tuple[Node, ...], edges: tuple[Edge, ...]) -> None:
    by_id = {node.id: node for node in nodes}
    if len(by_id) != len(nodes):
        raise ValueError("duplicate node id")

    incoming: dict[NodeId, int] = {node.id: 0 for node in nodes}
    outgoing: dict[NodeId, list[NodeId]] = {node.id: [] for node in nodes}
    for edge in edges:
        source_node = by_id.get(edge.source)
        target_node = by_id.get(edge.target)
        if source_node is None or target_node is None:
            raise ValueError("edge references unknown node")
        source_port = _port_by_name(source_node.outputs, edge.source_port)
        target_port = _port_by_name(target_node.inputs, edge.target_port)
        if source_port.kind != target_port.kind:
            raise ValueError("edge connects incompatible port kinds")
        if (
            source_port.schema is not None
            and target_port.schema is not None
            and source_port.schema != target_port.schema
        ):
            raise ValueError("edge connects incompatible schemas")
        outgoing[source_node.id].append(target_node.id)
        incoming[target_node.id] += 1

    ready = [node_id for node_id, count in incoming.items() if count == 0]
    heapq.heapify(ready)
    visited = 0
    while ready:
        current = heapq.heappop(ready)
        visited += 1
        for target_id in sorted(outgoing[current]):
            incoming[target_id] -= 1
            if incoming[target_id] == 0:
                heapq.heappush(ready, target_id)
    if visited != len(nodes):
        raise ValueError("pipeline contains a cycle")


def _port_by_name(ports: tuple[Port, ...], name: str) -> Port:
    matches = [port for port in ports if port.name == name]
    if len(matches) != 1:
        raise ValueError(f"port {name!r} does not exist exactly once")
    return matches[0]


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _node_semantic_payload(
    operator: OperatorRef,
    params: tuple[tuple[str, FrozenValue], ...],
    inputs: tuple[Port, ...],
    outputs: tuple[Port, ...],
) -> str:
    return _canonical_json(
        {
            "operator": {"name": operator.name, "version": operator.version},
            "params": {key: thaw_value(value) for key, value in params},
            "inputs": [_port_to_data(port) for port in inputs],
            "outputs": [_port_to_data(port) for port in outputs],
        }
    )


def _schema_to_data(schema: SchemaRef | None) -> object:
    if schema is None:
        return None
    return {"name": schema.name, "version": schema.version}


def _schema_from_data(value: object) -> SchemaRef | None:
    if value is None:
        return None
    data = _require_mapping(value, "schema")
    version = data.get("version")
    if version is not None and not isinstance(version, str):
        raise TypeError("schema.version must be a string or null")
    return SchemaRef(name=_require_str(data.get("name"), "schema.name"), version=version)


def _port_to_data(port: Port) -> dict[str, object]:
    return {"name": port.name, "kind": port.kind, "schema": _schema_to_data(port.schema)}


def _port_from_data(value: Mapping[str, object]) -> Port:
    kind = _require_str(value.get("kind"), "port.kind")
    if kind not in {"batch", "stream"}:
        raise ValueError("port.kind must be batch or stream")
    return Port(
        name=_require_str(value.get("name"), "port.name"),
        kind=cast(PortKind, kind),
        schema=_schema_from_data(value.get("schema")),
    )


def _node_to_data(node: Node) -> dict[str, object]:
    return {
        "id": node.id.value,
        "instance_key": node.instance_key,
        "operator": {"name": node.operator.name, "version": node.operator.version},
        "params": {key: thaw_value(value) for key, value in node.params},
        "inputs": [_port_to_data(port) for port in node.inputs],
        "outputs": [_port_to_data(port) for port in node.outputs],
        "origin": {"view": node.origin.view, "reference": node.origin.reference},
        "ownership": node.ownership,
        "label": node.label,
    }


def _node_from_data(value: Mapping[str, object]) -> Node:
    operator_data = _require_mapping(value.get("operator"), "operator")
    params = _require_mapping(value.get("params"), "params")
    inputs = _require_sequence(value.get("inputs"), "inputs")
    outputs = _require_sequence(value.get("outputs"), "outputs")
    origin = _require_mapping(value.get("origin"), "origin")
    ownership = _require_str(value.get("ownership"), "ownership")
    origin_view = _require_str(origin.get("view"), "origin.view")
    if ownership not in {"GRAPH", "USER", "RECONCILED"}:
        raise ValueError("invalid ownership")
    if origin_view not in {"graph", "notebook", "imported", "system"}:
        raise ValueError("invalid origin view")
    reference = origin.get("reference")
    label = value.get("label")
    if reference is not None and not isinstance(reference, str):
        raise TypeError("origin.reference must be a string or null")
    if label is not None and not isinstance(label, str):
        raise TypeError("label must be a string or null")

    operator = OperatorRef(
        name=_require_str(operator_data.get("name"), "operator.name"),
        version=_require_int(operator_data.get("version"), "operator.version"),
    )
    instance_key = _require_str(value.get("instance_key"), "instance_key")
    expected_id = NodeId(_require_str(value.get("id"), "id"))
    node = Node.create(
        operator=operator,
        instance_key=instance_key,
        params=params,
        inputs=tuple(_port_from_data(_require_mapping(item, "input")) for item in inputs),
        outputs=tuple(_port_from_data(_require_mapping(item, "output")) for item in outputs),
        origin=Origin(cast(OriginView, origin_view), reference),
        ownership=cast(Ownership, ownership),
        label=label,
    )
    if node.id != expected_id:
        raise ValueError("node id does not match semantic content and instance_key")
    return node


def _edge_to_data(edge: Edge) -> dict[str, object]:
    return {
        "source": edge.source.value,
        "source_port": edge.source_port,
        "target": edge.target.value,
        "target_port": edge.target_port,
    }


def _edge_from_data(value: Mapping[str, object]) -> Edge:
    return Edge(
        source=NodeId(_require_str(value.get("source"), "edge.source")),
        source_port=_require_str(value.get("source_port"), "edge.source_port"),
        target=NodeId(_require_str(value.get("target"), "edge.target")),
        target_port=_require_str(value.get("target_port"), "edge.target_port"),
    )


def _require_mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise TypeError(f"{name} must be an object with string keys")
    return cast(Mapping[str, object], value)


def _require_sequence(value: object, name: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise TypeError(f"{name} must be an array")
    return cast(Sequence[object], value)


def _require_str(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    return value


def _require_int(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{name} must be an integer")
    return value
