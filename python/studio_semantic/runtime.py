"""Runtime for executing compiled semantic metric and dashboard queries."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from time import monotonic
from typing import Protocol

from studio_sql import SqlEngine, SqlQueryResult, SqlResultLimitError, SqlTimeoutError
from studio_sql.wire import sql_wire_value

from .compiler import CompiledMetricQuery, compile_metric_query
from .contracts import DashboardDefinition, DashboardTile, MetricQuery, SemanticModel
from .joins import SemanticJoin, compile_join_chain, compile_join_query

MAX_DASHBOARD_TILES = 12
MAX_DASHBOARD_ROWS = 100_000
MAX_DASHBOARD_RESULT_BYTES = 8 * 1024 * 1024
MAX_DASHBOARD_METADATA_BYTES = 1 * 1024 * 1024
MAX_DASHBOARD_QUERY_BYTES = MAX_DASHBOARD_RESULT_BYTES - MAX_DASHBOARD_METADATA_BYTES
MAX_DASHBOARD_EXECUTION_MS = 15_000


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
        timeout_ms: int = 5_000,
        max_result_bytes: int = 1_048_576,
    ) -> SqlQueryResult: ...


def _prepare_dashboard_queries(
    models: dict[str, SemanticModel], dashboard: DashboardDefinition
) -> tuple[tuple[DashboardTile, CompiledMetricQuery], ...]:
    """Validate all fan-out and references before executing any dashboard SQL."""
    if len(dashboard.tiles) > MAX_DASHBOARD_TILES:
        raise ValueError(f"semantic dashboard exceeds {MAX_DASHBOARD_TILES} tiles")
    requested_rows = sum(tile.query.limit for tile in dashboard.tiles)
    if requested_rows > MAX_DASHBOARD_ROWS:
        raise ValueError(
            f"semantic dashboard exceeds the aggregate row budget of {MAX_DASHBOARD_ROWS}"
        )

    prepared: list[tuple[DashboardTile, CompiledMetricQuery]] = []
    for tile in dashboard.tiles:
        model = models.get(tile.query.model_id)
        if model is None:
            raise KeyError(f"dashboard references unknown semantic model: {tile.query.model_id}")
        # Compile every tile before starting the first query so a malformed or
        # stale later tile cannot cause needless partial work.
        prepared.append((tile, compile_metric_query(model, tile.query)))
    return tuple(prepared)


def _execute_dashboard_queries(
    prepared: tuple[tuple[DashboardTile, CompiledMetricQuery], ...],
    execute: Callable[[DashboardTile, CompiledMetricQuery, int, int], SqlQueryResult],
) -> tuple[DashboardTileResult, ...]:
    """Apply one response-byte and wall-clock budget across sequential tiles."""
    deadline = monotonic() + MAX_DASHBOARD_EXECUTION_MS / 1000
    remaining_bytes = MAX_DASHBOARD_QUERY_BYTES
    results: list[DashboardTileResult] = []
    for tile, compiled in prepared:
        timeout_ms = int((deadline - monotonic()) * 1000)
        if timeout_ms <= 0:
            raise SqlTimeoutError("semantic dashboard exceeded its total execution time limit")
        if remaining_bytes < 1:
            raise SqlResultLimitError("semantic dashboard exceeds its total response byte limit")
        result = execute(tile, compiled, timeout_ms, remaining_bytes)
        rows = [[sql_wire_value(value) for value in row] for row in result.rows]
        encoded_size = len(
            json.dumps(rows, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        )
        if encoded_size > remaining_bytes:
            raise SqlResultLimitError("semantic dashboard exceeds its total response byte limit")
        remaining_bytes -= encoded_size
        results.append(DashboardTileResult(tile.id, result))
    return tuple(results)


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
        prepared = _prepare_dashboard_queries(models, dashboard)

        def execute(
            tile: DashboardTile,
            compiled: CompiledMetricQuery,
            timeout_ms: int,
            max_result_bytes: int,
        ) -> SqlQueryResult:
            return self._engine.execute(
                compiled.sql,
                compiled.parameters,
                max_rows=tile.query.limit,
                timeout_ms=timeout_ms,
                max_result_bytes=max_result_bytes,
            )

        return _execute_dashboard_queries(prepared, execute)


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
        if not isinstance(project_id, str) or not project_id.strip():
            raise ValueError("project_id must be a non-empty string")
        prepared = _prepare_dashboard_queries(models, dashboard)

        def execute(
            tile: DashboardTile,
            compiled: CompiledMetricQuery,
            timeout_ms: int,
            max_result_bytes: int,
        ) -> SqlQueryResult:
            return self._engine.execute(
                project_id,
                compiled.sql,
                compiled.parameters,
                max_rows=tile.query.limit,
                timeout_ms=timeout_ms,
                max_result_bytes=max_result_bytes,
            )

        return _execute_dashboard_queries(prepared, execute)


__all__ = (
    "DashboardTileResult",
    "MAX_DASHBOARD_EXECUTION_MS",
    "MAX_DASHBOARD_METADATA_BYTES",
    "MAX_DASHBOARD_QUERY_BYTES",
    "MAX_DASHBOARD_RESULT_BYTES",
    "MAX_DASHBOARD_ROWS",
    "MAX_DASHBOARD_TILES",
    "ProjectScopedSemanticRuntime",
    "SemanticRuntime",
)
