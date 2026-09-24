"""Ronin plugin boundary for Data Enginerring Studio."""

from __future__ import annotations

import hashlib
import json
from typing import Any, cast

from studio_core.operators import builtin_operator_catalog
from studio_core.plugins import (
    PluginContext,
    PluginDependency,
    PluginManifest,
    SurfaceContribution,
)

from .compilations import SqliteCompilationStore
from .compiler import compile_pipeline
from .debugger import DebuggerService
from .execution import plan_pipeline_execution
from .ide import IdeCell
from .previews import preview_pipeline
from .revisions import RevisionApplication, RevisionArtifactStore, RevisionRecordStore
from .sdp_adapter import SdpProjectSource
from .worker import PipelineExecutionError, execute_pipeline_job


class DataEnginerringStudioPlugin:
    manifest = PluginManifest(
        id="com.sauronshepherd.ronin.data-enginerring-studio",
        name="Data Enginerring Studio",
        version="0.1.0",
        plugin_api="1.0",
        host_requires=">=1,<2",
        edition="community",
        capabilities=(
            "data-engineering.projects.v1",
            "data-engineering.pipelines.v1",
            "data-engineering.ir.v1",
            "data-engineering.compiler.v1",
            "data-engineering.preview.v1",
            "data-engineering.quality.v1",
            "data-engineering.lineage.v1",
            "data-engineering.runtime-provider.v1",
        ),
        dependencies=(PluginDependency("com.sauronshepherd.ronin.workspaces"),),
        permissions=(
            "data-engineering:read",
            "data-engineering:write",
            "data-engineering:execute",
        ),
        isolation="in_process",
        critical=False,
        job_types=("data-engineering.pipeline-run.v1",),
        event_types=(
            "data-engineering.pipeline-revision-created.v1",
            "data-engineering.run-completed.v1",
            "data-engineering.schema-drift-detected.v1",
        ),
        migration_ids=("data-engineering.schema.v1",),
        surface_ids=(
            "data-engineering.health.v1",
            "data-engineering.validate.v1",
            "data-engineering.preview.v1",
            "data-engineering.debugger.create.v1",
            "data-engineering.debugger.get.v1",
            "data-engineering.debugger.breakpoint.v1",
        ),
        ui_entry="studio_data_engineering.ui",
        config_schema="studio_data_engineering/config.schema.json",
    )

    def __init__(self) -> None:
        self.started = False
        self.context: PluginContext | None = None
        self._revisions: RevisionApplication | None = None
        self._compilations: SqliteCompilationStore | None = None
        self._debugger = DebuggerService()

    def register(self, context: PluginContext) -> None:
        self.context = context
        artifact_store = context.services.get("artifact_store")
        if artifact_store is not None:
            self._revisions = RevisionApplication(
                cast(RevisionArtifactStore, artifact_store),
                cast(RevisionRecordStore | None, context.services.get("revision_store")),
            )
        compilation_store = context.services.get("compilation_store")
        if isinstance(compilation_store, SqliteCompilationStore):
            self._compilations = compilation_store
        context.contributions.add_route(
            "GET",
            "/v1/data-engineering/health",
            context.plugin_id,
            self.health,
            permission="data-engineering:read",
        )
        context.contributions.add_route(
            "GET",
            "/v1/data-engineering/queryflux/capabilities",
            context.plugin_id,
            self.queryflux_capabilities,
            permission="data-engineering:read",
        )
        context.contributions.add_route(
            "POST",
            "/v1/data-engineering/debugger/sessions",
            context.plugin_id,
            self.debugger_create,
            permission="data-engineering:read",
        )
        context.contributions.add_route(
            "GET",
            "/v1/data-engineering/debugger/sessions/{session_id}",
            context.plugin_id,
            self.debugger_get,
            permission="data-engineering:read",
        )
        context.contributions.add_route(
            "POST",
            "/v1/data-engineering/debugger/sessions/{session_id}/breakpoints/{cell_id}",
            context.plugin_id,
            self.debugger_breakpoint,
            permission="data-engineering:read",
        )
        context.contributions.add_surface(
            SurfaceContribution(
                id="data-engineering.health.v1",
                plugin_id=context.plugin_id,
                namespace="data-engineering",
                command="health",
                operation_id="data-engineering.health.v1",
                capability="data-engineering.projects.v1",
                permission="data-engineering:read",
                path="/v1/data-engineering/health",
                method="GET",
                output_schema={"type": "object"},
            )
        )
        for contribution in (
            SurfaceContribution(
                id="data-engineering.debugger.create.v1",
                plugin_id=context.plugin_id,
                namespace="debugger",
                command="create",
                operation_id="data-engineering.debugger.create.v1",
                capability="data-engineering.pipelines.v1",
                permission="data-engineering:read",
                path="/v1/data-engineering/debugger/sessions",
                method="POST",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
            ),
            SurfaceContribution(
                id="data-engineering.debugger.get.v1",
                plugin_id=context.plugin_id,
                namespace="debugger",
                command="get",
                operation_id="data-engineering.debugger.get.v1",
                capability="data-engineering.pipelines.v1",
                permission="data-engineering:read",
                path="/v1/data-engineering/debugger/sessions/{session_id}",
                method="GET",
                output_schema={"type": "object"},
            ),
            SurfaceContribution(
                id="data-engineering.debugger.breakpoint.v1",
                plugin_id=context.plugin_id,
                namespace="debugger",
                command="breakpoint",
                operation_id="data-engineering.debugger.breakpoint.v1",
                capability="data-engineering.pipelines.v1",
                permission="data-engineering:read",
                path="/v1/data-engineering/debugger/sessions/{session_id}/breakpoints/{cell_id}",
                method="POST",
                output_schema={"type": "object"},
            ),
        ):
            context.contributions.add_surface(contribution)
        context.contributions.add_route(
            "GET",
            "/v1/data-engineering/runtimes",
            context.plugin_id,
            self.list_runtimes,
            permission="data-engineering:read",
        )
        context.contributions.add_surface(
            SurfaceContribution(
                id="data-engineering.validate.v1",
                plugin_id=context.plugin_id,
                namespace="data-engineering",
                command="validate",
                operation_id="data-engineering.validate.v1",
                capability="data-engineering.pipelines.v1",
                permission="data-engineering:read",
                path="/v1/data-engineering/pipelines/validate",
                method="POST",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
            )
        )
        context.contributions.add_route(
            "POST",
            "/v1/data-engineering/pipelines/validate",
            context.plugin_id,
            self.validate_pipeline,
            permission="data-engineering:read",
        )
        context.contributions.add_route(
            "POST",
            "/v1/data-engineering/pipelines/preview",
            context.plugin_id,
            self.preview_pipeline,
            permission="data-engineering:execute",
        )
        context.contributions.add_surface(
            SurfaceContribution(
                id="data-engineering.preview.v1",
                plugin_id=context.plugin_id,
                namespace="data-engineering",
                command="preview",
                operation_id="data-engineering.preview.v1",
                capability="data-engineering.preview.v1",
                permission="data-engineering:execute",
                path="/v1/data-engineering/pipelines/preview",
                method="POST",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
            )
        )
        context.contributions.add_route(
            "POST",
            "/v1/data-engineering/pipelines/runs",
            context.plugin_id,
            self.submit_run,
            permission="data-engineering:execute",
        )
        context.contributions.add_route(
            "POST",
            "/v1/data-engineering/sdp/import",
            context.plugin_id,
            self.import_sdp,
            permission="data-engineering:write",
        )
        context.contributions.add_route(
            "GET",
            "/v1/data-engineering/compilations/{revision_key}/{runtime}",
            context.plugin_id,
            self.get_compilation,
            permission="data-engineering:read",
        )
        context.contributions.add_route(
            "GET",
            "/v1/data-engineering/outbox/pending",
            context.plugin_id,
            self.pending_events,
            permission="data-engineering:read",
        )
        context.contributions.add_job(
            "data-engineering.pipeline-run.v1",
            context.plugin_id,
            self.run_pipeline,
        )
        context.contributions.add_migration("data-engineering.schema.v1", context.plugin_id)
        context.contributions.add_ui(
            context.plugin_id,
            {
                "uiApi": "1.0",
                "entry": "/studio/data-enginerring-studio.html",
                "assets": {
                    "html": "/studio/data-enginerring-studio.html",
                    "javascript": "/studio/data-enginerring-studio.js",
                    "stylesheet": "/studio/data-enginerring-studio.css",
                },
                "navigation": [
                    {
                        "id": "data-enginerring-studio",
                        "label": "Data Enginerring Studio",
                        "route": "/data-enginerring-studio",
                        "permission": "data-engineering:read",
                    }
                ],
                "routes": [
                    "/data-enginerring-studio/projects",
                    "/data-enginerring-studio/designer",
                    "/data-enginerring-studio/code",
                    "/data-enginerring-studio/runs",
                    "/data-enginerring-studio/lineage",
                    "/data-enginerring-studio/runtimes",
                ],
            },
        )

    def debugger_create(self, *, body: object | None = None, **_kwargs: Any) -> dict[str, object]:
        if not isinstance(body, dict) or not isinstance(body.get("session_id"), str):
            raise ValueError("debugger session requires session_id")
        cells = tuple(
            IdeCell(str(item["cell_id"]), str(item.get("source", "")))
            for item in body.get("cells", [])
            if isinstance(item, dict) and "cell_id" in item
        )
        return self._debugger.create(str(body["session_id"]), cells).to_payload()

    def debugger_get(self, session_id: str, **_kwargs: Any) -> dict[str, object]:
        return self._debugger.get(session_id).to_payload()

    def debugger_breakpoint(
        self, session_id: str, cell_id: str, **_kwargs: Any
    ) -> dict[str, object]:
        return self._debugger.breakpoint(session_id, cell_id).to_payload()

    def startup(self) -> None:
        self.started = True

    def shutdown(self) -> None:
        self.started = False

    def list_runtimes(self, **_kwargs: Any) -> dict[str, object]:
        self._assert_ready()
        return {
            "items": [
                {
                    "id": "local-preview",
                    "kind": "preview",
                    "capabilities": ["batch", "sample", "schema-inference"],
                    "status": "planned",
                },
                {
                    "id": "spark-connect",
                    "kind": "spark-connect",
                    "capabilities": ["batch", "dataframe", "logical-plan"],
                    "status": "planned",
                },
                {
                    "id": "spark-sdp",
                    "kind": "spark-declarative-pipelines",
                    "capabilities": ["declarative", "batch", "streaming"],
                    "status": "planned",
                },
            ]
        }

    def queryflux_capabilities(self, **_kwargs: Any) -> dict[str, object]:
        """Expose safe provider status without leaking cluster configuration."""

        self._assert_ready()
        return {
            "profile": "queryflux",
            "provider": "queryflux",
            "status": "not_configured",
            "target": "provider-neutral query engine",
            "capabilities": {
                "routing_trace": True,
                "bounded_preview": True,
                "cancellation": True,
            },
            "translation_policies": ["native_only", "best_effort", "strict"],
        }

    def health(self, **_kwargs: Any) -> dict[str, object]:
        return {
            "plugin": self.manifest.id,
            "status": "ready" if self.started else "starting",
            "revision_store": self._revisions is not None,
            "compilation_store": self._compilations is not None,
            "runtimes": {
                "local-preview": "ready",
                "spark-connect": "external-provider",
                "spark-sdp": "external-provider",
            },
        }

    def validate_pipeline(self, *, body: object | None = None, **_kwargs: Any) -> dict[str, object]:
        self._assert_ready()
        if not isinstance(body, dict):
            raise ValueError("pipeline body must be an object")
        runtime = body.get("runtime", "local-preview")
        pipeline = body.get("pipeline", body)
        if not isinstance(runtime, str) or not isinstance(pipeline, dict):
            raise ValueError("runtime must be a string and pipeline must be an object")
        report = compile_pipeline(pipeline, runtime=runtime, catalog=builtin_operator_catalog())
        ir_digest = hashlib.sha256(
            json.dumps(pipeline, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        revision_key = str(body.get("revision_key", "unpersisted"))
        if self._compilations is not None:
            self._compilations.save_report(
                revision_key=revision_key,
                ir_digest=ir_digest,
                report=report,
            )
            self._compilations.enqueue(
                event_id=f"compilation:{revision_key}:{runtime}:{ir_digest}",
                event_type="data-engineering.compilation-completed.v1",
                aggregate_key=revision_key,
                payload={
                    "revision_key": revision_key,
                    "runtime": runtime,
                    "ir_digest": ir_digest,
                    "portable": report.portable,
                },
            )
        return {
            "valid": report.portable,
            "contract": "data-engineering.ir.v1",
            "portable": report.portable,
            "runtime": report.runtime,
            "node_count": report.node_count,
            "edge_count": report.edge_count,
            "ir_digest": ir_digest,
            "diagnostics": [
                {
                    "code": item.code,
                    "message": item.message,
                    "path": item.path,
                    "severity": item.severity,
                }
                for item in report.diagnostics
            ],
        }

    def preview_pipeline(self, *, body: object | None = None, **_kwargs: Any) -> dict[str, object]:
        self._assert_ready()
        if not isinstance(body, dict):
            raise ValueError("pipeline body must be an object")
        pipeline = body.get("pipeline", body)
        fixtures = body.get("fixtures", {})
        row_limit = body.get("row_limit", 100)
        if not isinstance(pipeline, dict):
            raise ValueError("pipeline must be an object")
        if not isinstance(fixtures, dict) or not all(
            isinstance(key, str) and isinstance(value, list) for key, value in fixtures.items()
        ):
            raise ValueError("fixtures must be an object of arrays")
        if not isinstance(row_limit, int) or isinstance(row_limit, bool):
            raise ValueError("row_limit must be an integer")
        result = preview_pipeline(
            pipeline,
            fixtures=fixtures,
            row_limit=row_limit,
        )
        return {
            "status": "completed",
            "mode": "preview",
            "runtime": result.runtime,
            "rows_by_node": {key: list(rows) for key, rows in result.rows_by_node.items()},
            "metrics": dict(result.metrics),
            "diagnostics": list(result.diagnostics),
        }

    def submit_run(self, *, body: object | None = None, **_kwargs: Any) -> dict[str, object]:
        self._assert_ready()
        if not isinstance(body, dict):
            raise ValueError("pipeline run body must be an object")
        project_id = body.get("project_id")
        revision_key = body.get("revision_key")
        ir_digest = body.get("ir_digest")
        runtime = body.get("runtime", "local-preview")
        required = (project_id, revision_key, ir_digest, runtime)
        if not all(isinstance(value, str) for value in required):
            raise ValueError("project_id, revision_key, ir_digest and runtime are required strings")
        project_id = cast(str, project_id)
        revision_key = cast(str, revision_key)
        ir_digest = cast(str, ir_digest)
        runtime = cast(str, runtime)
        plan = plan_pipeline_execution(
            project_id=project_id,
            revision_key=revision_key,
            ir_digest=ir_digest,
            runtime=runtime,
            parameters=body.get("parameters") if isinstance(body.get("parameters"), dict) else None,
            now=body.get("now", "2026-09-19T00:00:00.000000Z"),
        )
        return {
            "status": "planned",
            "job_type": "data-engineering.pipeline-run.v1",
            "delegation": "jobs.execution.v1",
            "job_id": str(plan.job.id),
            "run_id": str(plan.run.id),
            "idempotency_key": plan.job.idempotency_key,
            "request_digest": plan.job.request_digest,
        }

    def import_sdp(
        self,
        *,
        body: object | None = None,
        idempotency_key: str | None = None,
        **_kwargs: Any,
    ) -> dict[str, object]:
        self._assert_ready()
        if not idempotency_key or not idempotency_key.strip():
            raise ValueError("Idempotency-Key is required")
        if not isinstance(body, dict):
            raise ValueError("import body must be an object")
        project_id = body.get("project_id")
        pipeline_id = body.get("pipeline_id")
        project_yaml = body.get("project_yaml")
        pipeline_documents = body.get("pipeline_documents", [])
        required = (project_id, pipeline_id, project_yaml)
        if not all(isinstance(value, str) and value.strip() for value in required):
            raise ValueError("project_id, pipeline_id and project_yaml are required strings")
        project_id = cast(str, project_id)
        pipeline_id = cast(str, pipeline_id)
        project_yaml = cast(str, project_yaml)
        if not isinstance(pipeline_documents, list):
            raise ValueError("pipeline_documents must be an array")
        documents: list[tuple[str, bytes]] = []
        for item in pipeline_documents:
            if (
                not isinstance(item, dict)
                or not isinstance(item.get("name"), str)
                or not isinstance(item.get("content"), str)
            ):
                raise ValueError("pipeline document requires string name and content")
            documents.append((item["name"], item["content"].encode("utf-8")))
        if self._revisions is None:
            raise RuntimeError("artifact store service is unavailable")
        expected_revision = body.get("expected_revision")
        record = self._revisions.import_sdp(
            project_id=project_id,
            pipeline_id=pipeline_id,
            source=SdpProjectSource(project_id, project_yaml.encode("utf-8"), tuple(documents)),
            expected_revision=expected_revision if isinstance(expected_revision, int) else None,
        )
        return {
            "project_id": record.project_id,
            "pipeline_id": record.pipeline_id,
            "revision": record.revision,
            "source_digest": record.source_digest,
            "project_artifact": record.project_artifact.storage_ref,
            "pipeline_artifacts": [
                {"name": name, "storage_ref": ref.storage_ref}
                for name, ref in record.pipeline_artifacts
            ],
            "metadata_artifact": record.metadata_artifact.storage_ref,
        }

    def get_compilation(self, revision_key: str, runtime: str, **_kwargs: Any) -> dict[str, object]:
        self._assert_ready()
        if self._compilations is None:
            raise RuntimeError("compilation store is unavailable")
        report = self._compilations.get_latest_report(revision_key=revision_key, runtime=runtime)
        if report is None:
            raise KeyError(f"compilation not found: {revision_key}/{runtime}")
        return dict(report)

    def pending_events(self, *, limit: int = 100, **_kwargs: Any) -> dict[str, object]:
        self._assert_ready()
        if self._compilations is None:
            raise RuntimeError("compilation store is unavailable")
        return {"items": list(self._compilations.pending_events(limit=limit))}

    def run_pipeline(self, payload: object | None = None, **_kwargs: Any) -> dict[str, object]:
        """Run a local-preview job; remote runtimes fail closed in the worker."""
        self._assert_ready()
        if not isinstance(payload, dict):
            raise ValueError("pipeline job payload must be an object")
        try:
            result = execute_pipeline_job(payload)
        except PipelineExecutionError as exc:
            return {
                "status": "failed",
                "error_code": exc.code,
                "message": str(exc),
                "retryable": exc.retryable,
            }
        return {
            "status": result.state,
            "runtime": result.runtime,
            "output": dict(result.output),
            "evidence": dict(result.evidence),
        }

    def _assert_ready(self) -> None:
        if not self.started:
            raise RuntimeError("Data Enginerring Studio plugin is not ready")


def factory() -> DataEnginerringStudioPlugin:
    return DataEnginerringStudioPlugin()


__all__ = ("DataEnginerringStudioPlugin", "factory")
