"""Runtime for executing compiled semantic metric and dashboard queries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from studio_sql import SqlEngine, SqlQueryResult

from .compiler import CompiledMetricQuery, compile_metric_query
from .contracts import DashboardDefinition, DashboardTile, MetricQuery, SemanticModel
from .joins import SemanticJoin, compile_join_chain, compile_join_query


@dataclass(frozen=True, slots=True)
class DashboardTileResult:
    tile_id: str
    result: SqlQueryResult


class ProjectScopedSqlEngine(Protocol):
    def execute(
        self,
        project_id: str,
        sql: str,
        parameters: tuple[object, ...] = (),
        *,
        max_rows: int = 10_000,
    ) -> SqlQueryResult: ...


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

    def execute_join(
        self,
        left: SemanticModel,
        right: SemanticModel,
        join: SemanticJoin,
        *,
        max_rows: int = 10_000,
    ) -> SqlQueryResult:
        """Execute one bounded, identifier-only semantic model join."""
        if max_rows < 1 or max_rows > 100_000:
            raise ValueError("semantic join max_rows must be between 1 and 100000")
        return self._engine.execute(compile_join_query(left, right, join), max_rows=max_rows)

    def execute_join_chain(
        self,
        base: SemanticModel,
        steps: tuple[tuple[SemanticModel, SemanticJoin], ...],
        *,
        max_rows: int = 10_000,
    ) -> SqlQueryResult:
        """Execute a bounded left-deep semantic join chain."""
        if max_rows < 1 or max_rows > 100_000:
            raise ValueError("semantic join max_rows must be between 1 and 100000")
        return self._engine.execute(compile_join_chain(base, steps), max_rows=max_rows)

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
                raise KeyError(
                    f"dashboard references unknown semantic model: {tile.query.model_id}"
                )
            results.append(self.execute_tile(model, tile))
        return tuple(results)


class ProjectScopedSemanticRuntime:
    """Semantic runtime over a project-scoped provider-neutral SQL engine."""

    def __init__(self, engine: ProjectScopedSqlEngine) -> None:
        self._engine = engine

    def execute_for_project(
        self, project_id: str, model: SemanticModel, query: MetricQuery
    ) -> SqlQueryResult:
        compiled = compile_metric_query(model, query)
        return self._engine.execute(
            project_id, compiled.sql, compiled.parameters, max_rows=query.limit
        )

    def execute_join_chain_for_project(
        self,
        project_id: str,
        base: SemanticModel,
        steps: tuple[tuple[SemanticModel, SemanticJoin], ...],
        *,
        max_rows: int = 10_000,
    ) -> SqlQueryResult:
        """Execute a bounded semantic join chain through a project-scoped engine."""
        if not isinstance(project_id, str) or not project_id.strip():
            raise ValueError("project_id must be a non-empty string")
        if max_rows < 1 or max_rows > 100_000:
            raise ValueError("semantic join max_rows must be between 1 and 100000")
        return self._engine.execute(project_id, compile_join_chain(base, steps), max_rows=max_rows)

    def execute_dashboard_for_project(
        self,
        project_id: str,
        models: dict[str, SemanticModel],
        dashboard: DashboardDefinition,
    ) -> tuple[DashboardTileResult, ...]:
        """Execute every dashboard tile through the project-scoped engine."""
        results: list[DashboardTileResult] = []
        for tile in dashboard.tiles:
            model = models.get(tile.query.model_id)
            if model is None:
                raise KeyError(
                    f"dashboard references unknown semantic model: {tile.query.model_id}"
                )
            results.append(
                DashboardTileResult(
                    tile.id, self.execute_for_project(project_id, model, tile.query)
                )
            )
        return tuple(results)


__all__ = ("DashboardTileResult", "ProjectScopedSemanticRuntime", "SemanticRuntime")
