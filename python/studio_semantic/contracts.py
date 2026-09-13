"""Canonical semantic-model, metric and dashboard contracts for Ronin Public v1."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, TypeAlias, cast

from studio_core.canonical_json import decode as decode_canonical_json
from studio_core.canonical_json import encode as encode_canonical_json

Aggregation: TypeAlias = Literal["sum", "count", "avg", "min", "max", "distinct_count"]
FilterOperator: TypeAlias = Literal["eq", "ne", "gt", "gte", "lt", "lte", "in"]
ChartKind: TypeAlias = Literal["table", "number", "bar", "line", "area"]

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _text(value: str, name: str) -> str:
    if not value or value != value.strip() or "\n" in value or "\r" in value or "\x00" in value:
        raise ValueError(f"{name} must be non-empty, trimmed, and single-line")
    return value


def _identifier(value: str, name: str) -> str:
    _text(value, name)
    if not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{name} must be a SQL-safe portable identifier")
    return value


@dataclass(frozen=True, order=True, slots=True)
class SemanticDimension:
    name: str
    column: str
    data_type: str = "string"

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _identifier(self.name, "dimension name"))
        object.__setattr__(self, "column", _identifier(self.column, "dimension column"))
        _text(self.data_type, "dimension data_type")

    def to_payload(self) -> dict[str, str]:
        return {"name": self.name, "column": self.column, "data_type": self.data_type}

    @classmethod
    def from_payload(cls, payload: object) -> SemanticDimension:
        if not isinstance(payload, Mapping) or set(payload) != {"name", "column", "data_type"}:
            raise ValueError("semantic dimension has invalid shape")
        if not all(isinstance(payload[key], str) for key in payload):
            raise ValueError("semantic dimension fields must be strings")
        return cls(cast(str, payload["name"]), cast(str, payload["column"]), cast(str, payload["data_type"]))


@dataclass(frozen=True, order=True, slots=True)
class SemanticMeasure:
    name: str
    aggregation: Aggregation
    column: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _identifier(self.name, "measure name"))
        if self.aggregation not in {"sum", "count", "avg", "min", "max", "distinct_count"}:
            raise ValueError("unsupported semantic aggregation")
        if self.column is not None:
            object.__setattr__(self, "column", _identifier(self.column, "measure column"))
        if self.aggregation != "count" and self.column is None:
            raise ValueError("non-count measure requires a column")

    def to_payload(self) -> dict[str, object]:
        return {"name": self.name, "aggregation": self.aggregation, "column": self.column}

    @classmethod
    def from_payload(cls, payload: object) -> SemanticMeasure:
        if not isinstance(payload, Mapping) or set(payload) != {"name", "aggregation", "column"}:
            raise ValueError("semantic measure has invalid shape")
        name = payload["name"]
        aggregation = payload["aggregation"]
        column = payload["column"]
        if not isinstance(name, str) or not isinstance(aggregation, str):
            raise ValueError("semantic measure identity fields must be strings")
        if column is not None and not isinstance(column, str):
            raise ValueError("semantic measure column must be string or null")
        if aggregation not in {"sum", "count", "avg", "min", "max", "distinct_count"}:
            raise ValueError("unsupported semantic aggregation")
        return cls(name, cast(Aggregation, aggregation), cast(str | None, column))


@dataclass(frozen=True, slots=True)
class SemanticModel:
    id: str
    name: str
    source: str
    dimensions: tuple[SemanticDimension, ...] = ()
    measures: tuple[SemanticMeasure, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _identifier(self.id, "semantic model id"))
        _text(self.name, "semantic model name")
        object.__setattr__(self, "source", _identifier(self.source, "semantic source"))
        dimensions = tuple(sorted(self.dimensions, key=lambda item: item.name))
        measures = tuple(sorted(self.measures, key=lambda item: item.name))
        dimension_names = [item.name for item in dimensions]
        measure_names = [item.name for item in measures]
        if len(dimension_names) != len(set(dimension_names)):
            raise ValueError("semantic dimension names must be unique")
        if len(measure_names) != len(set(measure_names)):
            raise ValueError("semantic measure names must be unique")
        if set(dimension_names) & set(measure_names):
            raise ValueError("semantic dimension and measure names must not overlap")
        object.__setattr__(self, "dimensions", dimensions)
        object.__setattr__(self, "measures", measures)

    def to_payload(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "source": self.source,
            "dimensions": [item.to_payload() for item in self.dimensions],
            "measures": [item.to_payload() for item in self.measures],
        }

    def to_json(self) -> str:
        return encode_canonical_json(self.to_payload()).decode("utf-8")

    @classmethod
    def from_json(cls, payload: str) -> SemanticModel:
        data = decode_canonical_json(payload)
        if not isinstance(data, Mapping) or set(data) != {"id", "name", "source", "dimensions", "measures"}:
            raise ValueError("semantic model has invalid shape")
        identifier = data["id"]
        name = data["name"]
        source = data["source"]
        dimensions = data["dimensions"]
        measures = data["measures"]
        if not all(isinstance(value, str) for value in (identifier, name, source)):
            raise ValueError("semantic model identity fields must be strings")
        if not isinstance(dimensions, list) or not isinstance(measures, list):
            raise ValueError("semantic model dimensions/measures must be arrays")
        return cls(
            cast(str, identifier),
            cast(str, name),
            cast(str, source),
            tuple(SemanticDimension.from_payload(item) for item in dimensions),
            tuple(SemanticMeasure.from_payload(item) for item in measures),
        )


@dataclass(frozen=True, order=True, slots=True)
class SemanticFilter:
    dimension: str
    operator: FilterOperator
    values: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "dimension", _identifier(self.dimension, "filter dimension"))
        if self.operator not in {"eq", "ne", "gt", "gte", "lt", "lte", "in"}:
            raise ValueError("unsupported semantic filter operator")
        values = tuple(self.values)
        if not values:
            raise ValueError("semantic filter requires at least one value")
        if self.operator != "in" and len(values) != 1:
            raise ValueError("non-in semantic filter requires exactly one value")
        object.__setattr__(self, "values", values)


@dataclass(frozen=True, slots=True)
class MetricQuery:
    model_id: str
    measures: tuple[str, ...]
    dimensions: tuple[str, ...] = ()
    filters: tuple[SemanticFilter, ...] = ()
    limit: int = 10_000

    def __post_init__(self) -> None:
        object.__setattr__(self, "model_id", _identifier(self.model_id, "metric query model_id"))
        measures = tuple(sorted(_identifier(value, "metric measure") for value in self.measures))
        dimensions = tuple(sorted(_identifier(value, "metric dimension") for value in self.dimensions))
        if not measures:
            raise ValueError("metric query requires at least one measure")
        if len(measures) != len(set(measures)) or len(dimensions) != len(set(dimensions)):
            raise ValueError("metric query fields must be unique")
        if self.limit < 1 or self.limit > 100_000:
            raise ValueError("metric query limit must be between 1 and 100000")
        object.__setattr__(self, "measures", measures)
        object.__setattr__(self, "dimensions", dimensions)
        object.__setattr__(self, "filters", tuple(sorted(self.filters)))


@dataclass(frozen=True, slots=True)
class DashboardTile:
    id: str
    title: str
    chart: ChartKind
    query: MetricQuery

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _identifier(self.id, "dashboard tile id"))
        _text(self.title, "dashboard tile title")
        if self.chart not in {"table", "number", "bar", "line", "area"}:
            raise ValueError("unsupported dashboard chart kind")


@dataclass(frozen=True, slots=True)
class DashboardDefinition:
    id: str
    name: str
    tiles: tuple[DashboardTile, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _identifier(self.id, "dashboard id"))
        _text(self.name, "dashboard name")
        tiles = tuple(sorted(self.tiles, key=lambda tile: tile.id))
        ids = [tile.id for tile in tiles]
        if not tiles:
            raise ValueError("dashboard requires at least one tile")
        if len(ids) != len(set(ids)):
            raise ValueError("dashboard tile ids must be unique")
        object.__setattr__(self, "tiles", tiles)


__all__ = (
    "Aggregation",
    "ChartKind",
    "DashboardDefinition",
    "DashboardTile",
    "FilterOperator",
    "MetricQuery",
    "SemanticDimension",
    "SemanticFilter",
    "SemanticMeasure",
    "SemanticModel",
)
