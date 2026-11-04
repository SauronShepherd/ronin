"""Semantic metrics and dashboard query runtime for Ronin Public v1."""

from .bundle import (
    MAX_SEMANTIC_BUNDLE_BYTES,
    SemanticBundleImportPlan,
    SemanticBundleImportStore,
    SemanticBundleTooLarge,
    build_semantic_bundle,
    commit_semantic_bundle_import,
    export_semantic_bundle,
    plan_semantic_bundle_import,
)
from .compiler import CompiledMetricQuery, SemanticQueryError, compile_metric_query
from .contracts import (
    Aggregation,
    ChartKind,
    DashboardDefinition,
    DashboardTile,
    FilterOperator,
    MetricQuery,
    SemanticDimension,
    SemanticFilter,
    SemanticMeasure,
    SemanticModel,
)
from .joins import JoinType, SemanticJoin, compile_join_chain, compile_join_query, compile_join_sql
from .runtime import (
    MAX_DASHBOARD_EXECUTION_MS,
    MAX_DASHBOARD_METADATA_BYTES,
    MAX_DASHBOARD_QUERY_BYTES,
    MAX_DASHBOARD_RESULT_BYTES,
    MAX_DASHBOARD_ROWS,
    MAX_DASHBOARD_TILES,
    DashboardTileResult,
    ProjectScopedSemanticRuntime,
    SemanticRuntime,
)
from .scope import semantic_project_scope
from .store import SemanticModelConflict, SqliteSemanticStore

__all__ = (
    "Aggregation",
    "ChartKind",
    "CompiledMetricQuery",
    "DashboardDefinition",
    "DashboardTile",
    "DashboardTileResult",
    "MAX_DASHBOARD_EXECUTION_MS",
    "MAX_DASHBOARD_METADATA_BYTES",
    "MAX_DASHBOARD_QUERY_BYTES",
    "MAX_DASHBOARD_RESULT_BYTES",
    "MAX_DASHBOARD_ROWS",
    "MAX_DASHBOARD_TILES",
    "FilterOperator",
    "MetricQuery",
    "SemanticDimension",
    "SemanticFilter",
    "SemanticMeasure",
    "SemanticModel",
    "SemanticQueryError",
    "SemanticRuntime",
    "ProjectScopedSemanticRuntime",
    "SemanticModelConflict",
    "SqliteSemanticStore",
    "compile_metric_query",
    "JoinType",
    "SemanticJoin",
    "compile_join_chain",
    "compile_join_sql",
    "compile_join_query",
    "SemanticHTTPAdapter",
    "SemanticBundleImportPlan",
    "MAX_SEMANTIC_BUNDLE_BYTES",
    "SemanticBundleTooLarge",
    "semantic_project_scope",
    "SemanticBundleImportStore",
    "build_semantic_bundle",
    "commit_semantic_bundle_import",
    "export_semantic_bundle",
    "plan_semantic_bundle_import",
)
from .http import SemanticHTTPAdapter
