"""Compile safe semantic metric queries to parameterized SQL."""

from __future__ import annotations

from dataclasses import dataclass

from .contracts import MetricQuery, SemanticMeasure, SemanticModel


class SemanticQueryError(ValueError):
    """Raised when a query references unknown or unsupported semantic fields."""


@dataclass(frozen=True, slots=True)
class CompiledMetricQuery:
    sql: str
    parameters: tuple[object, ...]


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _measure_sql(measure: SemanticMeasure) -> str:
    if measure.aggregation == "count":
        expression = "COUNT(*)" if measure.column is None else f"COUNT({_quote(measure.column)})"
    elif measure.aggregation == "distinct_count":
        assert measure.column is not None
        expression = f"COUNT(DISTINCT {_quote(measure.column)})"
    else:
        assert measure.column is not None
        function = measure.aggregation.upper()
        expression = f"{function}({_quote(measure.column)})"
    return f"{expression} AS {_quote(measure.name)}"


def compile_metric_query(model: SemanticModel, query: MetricQuery) -> CompiledMetricQuery:
    if query.model_id != model.id:
        raise SemanticQueryError("metric query model_id does not match semantic model")

    dimensions = {item.name: item for item in model.dimensions}
    measures = {item.name: item for item in model.measures}
    unknown_dimensions = set(query.dimensions) - set(dimensions)
    unknown_measures = set(query.measures) - set(measures)
    unknown_filters = {item.dimension for item in query.filters} - set(dimensions)
    if unknown_dimensions:
        raise SemanticQueryError(f"unknown dimensions: {sorted(unknown_dimensions)}")
    if unknown_measures:
        raise SemanticQueryError(f"unknown measures: {sorted(unknown_measures)}")
    if unknown_filters:
        raise SemanticQueryError(f"unknown filter dimensions: {sorted(unknown_filters)}")

    select_parts = [
        f"{_quote(dimensions[name].column)} AS {_quote(name)}"
        for name in query.dimensions
    ]
    select_parts.extend(_measure_sql(measures[name]) for name in query.measures)

    parameters: list[object] = []
    predicates: list[str] = []
    operators = {
        "eq": "=",
        "ne": "<>",
        "gt": ">",
        "gte": ">=",
        "lt": "<",
        "lte": "<=",
    }
    for item in query.filters:
        column = _quote(dimensions[item.dimension].column)
        if item.operator == "in":
            placeholders = ", ".join("?" for _ in item.values)
            predicates.append(f"{column} IN ({placeholders})")
            parameters.extend(item.values)
        else:
            predicates.append(f"{column} {operators[item.operator]} ?")
            parameters.append(item.values[0])

    sql = f"SELECT {', '.join(select_parts)} FROM {_quote(model.source)}"
    if predicates:
        sql += " WHERE " + " AND ".join(predicates)
    if query.dimensions:
        group_columns = ", ".join(_quote(dimensions[name].column) for name in query.dimensions)
        sql += f" GROUP BY {group_columns}"
        sql += " ORDER BY " + ", ".join(_quote(name) for name in query.dimensions)
    sql += f" LIMIT {query.limit}"
    return CompiledMetricQuery(sql, tuple(parameters))


__all__ = ("CompiledMetricQuery", "SemanticQueryError", "compile_metric_query")
