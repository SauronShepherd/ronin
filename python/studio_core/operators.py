"""Provider-neutral operator contracts and deterministic catalog validation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal, TypeAlias

from .ir import FrozenList, FrozenMap, FrozenValue, Node, OperatorRef, Port, PortKind, thaw_value

ParameterKind: TypeAlias = Literal[
    "any",
    "array",
    "boolean",
    "expression",
    "integer",
    "number",
    "object",
    "string",
]
Cardinality: TypeAlias = Literal["one", "many"]


def _require_text(value: str, field_name: str, *, max_length: int = 500) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")
    if "\n" in value or "\r" in value:
        raise ValueError(f"{field_name} must not contain line breaks")
    if len(value) > max_length:
        raise ValueError(f"{field_name} must be at most {max_length} characters")


def _canonical_texts(values: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    for value in values:
        _require_text(value, field_name)
    canonical = tuple(sorted(values))
    if len(canonical) != len(set(canonical)):
        raise ValueError(f"{field_name} values must be unique")
    return canonical


@dataclass(frozen=True, order=True, slots=True)
class OperatorPort:
    """Logical operator port independent of any engine runtime object model."""

    name: str
    data_kind: str = "tabular"
    cardinality: Cardinality = "one"
    optional: bool = False

    def __post_init__(self) -> None:
        _require_text(self.name, "operator port name")
        _require_text(self.data_kind, "operator port data kind")
        if self.cardinality not in {"one", "many"}:
            raise ValueError("operator port cardinality must be one or many")


@dataclass(frozen=True, order=True, slots=True)
class OperatorParameter:
    """Semantic parameter declaration; UI widgets and secrets stay outside core."""

    name: str
    kind: ParameterKind = "any"
    required: bool = False

    def __post_init__(self) -> None:
        _require_text(self.name, "operator parameter name")
        if self.kind not in {
            "any",
            "array",
            "boolean",
            "expression",
            "integer",
            "number",
            "object",
            "string",
        }:
            raise ValueError("unsupported operator parameter kind")


@dataclass(frozen=True, slots=True)
class OperatorContract:
    """Portable semantic contract for one version of an operator."""

    ref: OperatorRef
    title: str
    category: str
    inputs: tuple[OperatorPort, ...] = ()
    outputs: tuple[OperatorPort, ...] = ()
    parameters: tuple[OperatorParameter, ...] = ()
    modes: tuple[PortKind, ...] = ("batch", "stream")
    required_capabilities: tuple[str, ...] = ()
    forbidden_capabilities: tuple[str, ...] = ()
    documentation_key: str | None = None
    allow_extra_parameters: bool = False

    def __post_init__(self) -> None:
        _require_text(self.ref.name, "operator name")
        _require_text(self.title, "operator title")
        _require_text(self.category, "operator category")
        canonical_inputs = tuple(sorted(self.inputs))
        canonical_outputs = tuple(sorted(self.outputs))
        canonical_parameters = tuple(sorted(self.parameters))
        _require_unique_names(canonical_inputs, "operator input port")
        _require_unique_names(canonical_outputs, "operator output port")
        _require_unique_names(canonical_parameters, "operator parameter")
        if not self.modes:
            raise ValueError("operator modes must be non-empty")
        if any(mode not in {"batch", "stream"} for mode in self.modes):
            raise ValueError("operator mode must be batch or stream")
        canonical_modes = tuple(sorted(set(self.modes)))
        required = _canonical_texts(self.required_capabilities, "required capability")
        forbidden = _canonical_texts(self.forbidden_capabilities, "forbidden capability")
        if set(required) & set(forbidden):
            raise ValueError("operator capabilities cannot be both required and forbidden")
        if self.documentation_key is not None:
            _require_text(self.documentation_key, "operator documentation key")
        object.__setattr__(self, "inputs", canonical_inputs)
        object.__setattr__(self, "outputs", canonical_outputs)
        object.__setattr__(self, "parameters", canonical_parameters)
        object.__setattr__(self, "modes", canonical_modes)
        object.__setattr__(self, "required_capabilities", required)
        object.__setattr__(self, "forbidden_capabilities", forbidden)

    def to_data(self) -> dict[str, object]:
        return {
            "ref": {"name": self.ref.name, "version": self.ref.version},
            "title": self.title,
            "category": self.category,
            "inputs": [_port_to_data(port) for port in self.inputs],
            "outputs": [_port_to_data(port) for port in self.outputs],
            "parameters": [_parameter_to_data(parameter) for parameter in self.parameters],
            "modes": list(self.modes),
            "required_capabilities": list(self.required_capabilities),
            "forbidden_capabilities": list(self.forbidden_capabilities),
            "documentation_key": self.documentation_key,
            "allow_extra_parameters": self.allow_extra_parameters,
        }


@dataclass(frozen=True, slots=True)
class OperatorCatalog:
    """Canonical, version-aware operator contract collection."""

    operators: tuple[OperatorContract, ...] = ()

    def __post_init__(self) -> None:
        canonical = tuple(sorted(self.operators, key=lambda item: (item.ref.name, item.ref.version)))
        refs = [operator.ref for operator in canonical]
        if len(refs) != len(set(refs)):
            raise ValueError("operator references must be unique within a catalog")
        object.__setattr__(self, "operators", canonical)

    def get(self, ref: OperatorRef) -> OperatorContract | None:
        return next((operator for operator in self.operators if operator.ref == ref), None)

    def latest(self, name: str) -> OperatorContract | None:
        matches = [operator for operator in self.operators if operator.ref.name == name]
        return max(matches, key=lambda item: item.ref.version, default=None)

    def to_data(self) -> dict[str, object]:
        return {"operators": [operator.to_data() for operator in self.operators]}

    def to_json(self) -> str:
        return json.dumps(self.to_data(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


@dataclass(frozen=True, order=True, slots=True)
class OperatorViolation:
    """Stable validation evidence for an operator/node contract mismatch."""

    code: str
    message: str
    path: str | None = None


def validate_operator_node(node: Node, catalog: OperatorCatalog) -> tuple[OperatorViolation, ...]:
    """Validate authored node semantics against a portable operator contract."""
    contract = catalog.get(node.operator)
    if contract is None:
        return (
            OperatorViolation(
                "RONIN-OP-001",
                f"operator contract is not available: {node.operator.name}@{node.operator.version}",
            ),
        )

    violations: list[OperatorViolation] = []
    parameters = dict(node.params)
    declared_parameters = {parameter.name: parameter for parameter in contract.parameters}
    for parameter in contract.parameters:
        if parameter.required and (
            parameter.name not in parameters or _is_missing(parameters[parameter.name])
        ):
            violations.append(
                OperatorViolation(
                    "RONIN-OP-002",
                    f"required operator parameter is missing: {parameter.name}",
                    f"params.{parameter.name}",
                )
            )
            continue
        if parameter.name in parameters and not _is_missing(parameters[parameter.name]):
            if not _matches_parameter_kind(parameters[parameter.name], parameter.kind):
                violations.append(
                    OperatorViolation(
                        "RONIN-OP-003",
                        f"operator parameter has incompatible type: {parameter.name}",
                        f"params.{parameter.name}",
                    )
                )
    if not contract.allow_extra_parameters:
        for name in sorted(set(parameters) - set(declared_parameters)):
            violations.append(
                OperatorViolation(
                    "RONIN-OP-004",
                    f"operator parameter is not declared by the contract: {name}",
                    f"params.{name}",
                )
            )

    violations.extend(_validate_ports(node.inputs, contract.inputs, "inputs"))
    violations.extend(_validate_ports(node.outputs, contract.outputs, "outputs"))
    observed_modes = sorted({port.kind for port in (*node.inputs, *node.outputs)})
    for mode in observed_modes:
        if mode not in contract.modes:
            violations.append(
                OperatorViolation(
                    "RONIN-OP-007",
                    f"operator does not support {mode} ports",
                    "ports",
                )
            )
    return tuple(sorted(violations))


def builtin_operator_catalog() -> OperatorCatalog:
    """Return the portable seed catalog adapted from mature SDP Studio semantics."""
    unary_input = (OperatorPort("in"),)
    unary_output = (OperatorPort("out"),)
    return OperatorCatalog(
        (
            OperatorContract(
                OperatorRef("source.table"),
                "Table",
                "sources",
                outputs=unary_output,
                parameters=(OperatorParameter("table", "string", required=True),),
                documentation_key="operator.source.table",
            ),
            OperatorContract(
                OperatorRef("source.file"),
                "File",
                "sources",
                outputs=unary_output,
                parameters=(
                    OperatorParameter("format", "string", required=True),
                    OperatorParameter("options", "object"),
                    OperatorParameter("path", "string", required=True),
                ),
                documentation_key="operator.source.file",
            ),
            OperatorContract(
                OperatorRef("transform.filter"),
                "Filter",
                "transforms",
                inputs=unary_input,
                outputs=unary_output,
                parameters=(OperatorParameter("expression", "expression", required=True),),
                documentation_key="operator.transform.filter",
            ),
            OperatorContract(
                OperatorRef("transform.select"),
                "Select",
                "transforms",
                inputs=unary_input,
                outputs=unary_output,
                parameters=(OperatorParameter("columns", "array", required=True),),
                documentation_key="operator.transform.select",
            ),
            OperatorContract(
                OperatorRef("transform.derive"),
                "Derive Column",
                "transforms",
                inputs=unary_input,
                outputs=unary_output,
                parameters=(
                    OperatorParameter("expression", "expression", required=True),
                    OperatorParameter("name", "string", required=True),
                ),
                documentation_key="operator.transform.derive",
            ),
            OperatorContract(
                OperatorRef("transform.join"),
                "Join",
                "transforms",
                inputs=(OperatorPort("left"), OperatorPort("right")),
                outputs=unary_output,
                parameters=(
                    OperatorParameter("condition", "expression", required=True),
                    OperatorParameter("how", "string", required=True),
                ),
                documentation_key="operator.transform.join",
            ),
            OperatorContract(
                OperatorRef("quality.row_count_range"),
                "Row Count Range",
                "quality",
                inputs=unary_input,
                outputs=unary_output,
                parameters=(
                    OperatorParameter("maximum", "integer"),
                    OperatorParameter("minimum", "integer"),
                ),
                documentation_key="operator.quality.row_count_range",
            ),
            OperatorContract(
                OperatorRef("dataset.materialized_view"),
                "Materialized View",
                "outputs",
                inputs=unary_input,
                outputs=unary_output,
                parameters=(OperatorParameter("name", "string", required=True),),
                documentation_key="operator.dataset.materialized_view",
            ),
        )
    )


def _require_unique_names(values: tuple[object, ...], field_name: str) -> None:
    names = [getattr(value, "name") for value in values]
    if len(names) != len(set(names)):
        raise ValueError(f"{field_name} names must be unique")


def _port_to_data(port: OperatorPort) -> dict[str, object]:
    return {
        "name": port.name,
        "data_kind": port.data_kind,
        "cardinality": port.cardinality,
        "optional": port.optional,
    }


def _parameter_to_data(parameter: OperatorParameter) -> dict[str, object]:
    return {
        "name": parameter.name,
        "kind": parameter.kind,
        "required": parameter.required,
    }


def _is_missing(value: FrozenValue) -> bool:
    return value is None or value == ""


def _matches_parameter_kind(value: FrozenValue, kind: ParameterKind) -> bool:
    if kind == "any":
        return True
    if kind in {"string", "expression"}:
        return isinstance(value, str)
    if kind == "boolean":
        return isinstance(value, bool)
    if kind == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if kind == "array":
        return isinstance(value, FrozenList)
    if kind == "object":
        return isinstance(value, FrozenMap)
    raise AssertionError(f"unhandled operator parameter kind: {kind}")


def _validate_ports(
    actual: tuple[Port, ...], declared: tuple[OperatorPort, ...], direction: str
) -> list[OperatorViolation]:
    actual_names = [port.name for port in actual]
    declared_by_name = {port.name: port for port in declared}
    violations: list[OperatorViolation] = []
    for name in sorted(set(actual_names)):
        if actual_names.count(name) > 1:
            violations.append(
                OperatorViolation(
                    "RONIN-OP-005",
                    f"node {direction} contain duplicate port: {name}",
                    f"{direction}.{name}",
                )
            )
        if name not in declared_by_name:
            violations.append(
                OperatorViolation(
                    "RONIN-OP-006",
                    f"node {direction} contain undeclared port: {name}",
                    f"{direction}.{name}",
                )
            )
    for port in declared:
        if not port.optional and port.name not in actual_names:
            violations.append(
                OperatorViolation(
                    "RONIN-OP-005",
                    f"node {direction} are missing required port: {port.name}",
                    f"{direction}.{port.name}",
                )
            )
    return violations


def operator_parameter_value(node: Node, name: str) -> object | None:
    """Expose a thawed parameter value to presentation/adapters without mutable core state."""
    value = node.param(name)
    return thaw_value(value) if value is not None else None
