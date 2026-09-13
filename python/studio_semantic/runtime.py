"""Runtime for executing compiled semantic metric and dashboard queries."""

from __future__ import annotations

from dataclasses import dataclass

from studio_sql import SqlEngine, SqlQueryResult

from .compiler import CompiledMetricQuery, compile_metric_query
from .contracts import DashboardDefinition, DashboardTile, MetricQuery, SemanticModel


@dataclass(frozen=True, slots=True)
class DashboardTileResult:
    tile_id: str
    result: SqlQueryResult


class SemanticRuntime:
    """Execute semantic queries against one provider-neutral SQL engine."""

    def __init__(self, engine: SqlEngine) -> None:
        self._engine = engine

    def compile(self, model: SemanticModel, query: MetricQuery) -> CompiledMetricQuery:
        return compile_metric_query(model, query)

    def execute(self, model: SemanticModel, query: MetricQuery) -> SqlQueryResult:
        compiled = self.compile(model, query)
        return self._engine.execute(
            compiled.sql,
            compiled.parameters,
            max_rows=query.limit,
        )

    def execute_tile(self, model: SemanticModel, tile: DashboardTile) -> DashboardTileResult:
        return DashboardTileResult(tile.id, self.execute(model, tile.query))

    def execute_dashboard(
        self,
        models: dict[str, SemanticModel],
        dashboard: DashboardDefinition,
    ) -> tuple[DashboardTileResult, ...]:
        results: list[DashboardTileResult] = []
        for tile in dashboard.tiles:
            model = models.get(tile.query.model_id)
            if model is None:
                raise KeyError(f"dashboard references unknown semantic model: {tile.query.model_id}")
            results.append(self.execute_tile(model, tile))
        return tuple(results)


__all__ = ("DashboardTileResult", "SemanticRuntime")
