"""Immutable, canonical and provider-neutral intermediate representation."""

from __future__ import annotations

import json
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


@dataclass(frozen=True, slots=True)
class Node:
    id: NodeId
    operator: OperatorRef
    params: tuple[tuple[str, FrozenValue], ...] = ()
    inputs: tuple[Port, ...] = ()
    outputs: tuple[Port, ...] = ()
    origin: Origin = DEFAULT_ORIGIN
    ownership: Ownership = "GRAPH"
    label: str | None = field(default=None, compare=False, hash=False)

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
        canonical_inputs = tuple(sorted(inputs))
        canonical_outputs = tuple(sorted(outputs))
        semantic = _canonical_json(
            {
                "operator": {"name": operator.name, "version": operator.version},
                "params": {key: thaw_value(value) for key, value in frozen_params},
                "inputs": [_port_to_data(port) for port in canonical_inputs],
                "outputs": [_port_to_data(port) for port in canonical_outputs],
            }
        )
        return cls(
            id=NodeId.derive(semantic, instance_key),
            operator=operator,
            params=frozen_params,
            inputs=canonical_inputs,
            outputs=canonical_outputs,
            origin=origin,
            ownership=ownership,
            label=label,
        )

    def param(self, name: str) -> FrozenValue | None:
        return dict(self.params).get(name)


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

    ready = sorted(node_id for node_id, count in incoming.items() if count == 0)
    visited = 0
    while ready:
        current = ready.pop(0)
        visited += 1
        for target_id in sorted(outgoing[current]):
            incoming[target_id] -= 1
            if incoming[target_id] == 0:
                ready.append(target_id)
                ready.sort()
    if visited != len(nodes):
        raise ValueError("pipeline contains a cycle")


def _port_by_name(ports: tuple[Port, ...], name: str) -> Port:
    matches = [port for port in ports if port.name == name]
    if len(matches) != 1:
        raise ValueError(f"port {name!r} does not exist exactly once")
    return matches[0]


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


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
        "operator": {"name": node.operator.name, "version": node.operator.version},
        "params": {key: thaw_value(value) for key, value in node.params},
        "inputs": [_port_to_data(port) for port in node.inputs],
        "outputs": [_port_to_data(port) for port in node.outputs],
        "origin": {"view": node.origin.view, "reference": node.origin.reference},
        "ownership": node.ownership,
        "label": node.label,
    }


def _node_from_data(value: Mapping[str, object]) -> Node:
    operator = _require_mapping(value.get("operator"), "operator")
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
    return Node(
        id=NodeId(_require_str(value.get("id"), "id")),
        operator=OperatorRef(
            name=_require_str(operator.get("name"), "operator.name"),
            version=_require_int(operator.get("version"), "operator.version"),
        ),
        params=tuple(sorted(((key, freeze_value(child)) for key, child in params.items()))),
        inputs=tuple(sorted(_port_from_data(_require_mapping(item, "input")) for item in inputs)),
        outputs=tuple(
            sorted(_port_from_data(_require_mapping(item, "output")) for item in outputs)
        ),
        origin=Origin(cast(OriginView, origin_view), reference),
        ownership=cast(Ownership, ownership),
        label=label,
    )


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
