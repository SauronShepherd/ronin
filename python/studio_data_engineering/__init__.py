"""Data Enginerring Studio plugin boundary."""

from .compilations import SqliteCompilationStore, publish_pending_compilation_events
from .compiler import CompilationReport, CompileDiagnostic, compile_pipeline
from .debugger import DebuggerService, DebugSnapshot, snapshot
from .evidence import persist_pipeline_evidence, persist_query_engine_evidence
from .execution import PipelineExecutionPlan, plan_pipeline_execution
from .execution_bridge import (
    attach_pipeline_evidence,
    cancel_pipeline,
    pipeline_evidence,
    pipeline_status,
    submit_pipeline_plan,
)
from .ide import IdeCell, IdeSession, execute_ide_session
from .lineage import LineageCatalog, publish_lineage_event, record_pipeline_lineage
from .pipeline_contracts import PipelineParameter, PipelineParameterSchema
from .plugin import DataEnginerringStudioPlugin, factory
from .postgres_revisions import PostgresRevisionDependencyError, PostgresRevisionStore
from .previews import PreviewError, PreviewResult, preview_pipeline
from .query_execution import QueryExecutionResult, QueryTransport, execute_query
from .revisions import PipelineRevisionRecord, RevisionApplication, RevisionConflict
from .runtimes import (
    QueryEngineRuntimeProvider,
    RuntimeHandshake,
    RuntimeProvider,
    local_runtime_handshake,
    negotiate_runtime,
)
from .sdp_adapter import SdpImportReport, SdpProjectSource, SdpStudioProvider
from .spark_connect import SparkConnectProvider, SparkConnectResult, SparkConnectUnavailable
from .sql_editor import (
    SqlExecutionRecord,
    SqliteSqlEditorStore,
    SqlQueryRevision,
    export_sql_rows,
)
from .sqlite_revisions import SqliteRevisionStore
from .worker import PipelineExecutionError, PipelineWorkerResult, execute_pipeline_job

__all__ = (
    "CompileDiagnostic",
    "CompilationReport",
    "DataEnginerringStudioPlugin",
    "compile_pipeline",
    "DebugSnapshot",
    "DebuggerService",
    "snapshot",
    "SqliteCompilationStore",
    "publish_pending_compilation_events",
    "PipelineExecutionPlan",
    "LineageCatalog",
    "record_pipeline_lineage",
    "publish_lineage_event",
    "IdeCell",
    "IdeSession",
    "execute_ide_session",
    "plan_pipeline_execution",
    "submit_pipeline_plan",
    "attach_pipeline_evidence",
    "pipeline_status",
    "cancel_pipeline",
    "pipeline_evidence",
    "persist_pipeline_evidence",
    "persist_query_engine_evidence",
    "QueryExecutionResult",
    "QueryTransport",
    "execute_query",
    "PipelineExecutionError",
    "PipelineParameter",
    "PipelineParameterSchema",
    "PipelineWorkerResult",
    "execute_pipeline_job",
    "factory",
    "PreviewError",
    "PreviewResult",
    "preview_pipeline",
    "SdpImportReport",
    "SdpProjectSource",
    "SdpStudioProvider",
    "PipelineRevisionRecord",
    "RevisionApplication",
    "RevisionConflict",
    "SqliteRevisionStore",
    "PostgresRevisionDependencyError",
    "PostgresRevisionStore",
    "SqlExecutionRecord",
    "export_sql_rows",
    "SqlQueryRevision",
    "SqliteSqlEditorStore",
    "RuntimeHandshake",
    "QueryEngineRuntimeProvider",
    "RuntimeProvider",
    "local_runtime_handshake",
    "negotiate_runtime",
    "SparkConnectProvider",
    "SparkConnectResult",
    "SparkConnectUnavailable",
)
