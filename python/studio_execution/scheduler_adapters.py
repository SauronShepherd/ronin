"""Explicit dispatch boundary for scheduler workload families."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

from studio_connectors import IngestionSyncCancelled, IngestionSyncDefinition
from studio_core import AssetId, AssetRef
from studio_observability import NotificationIntent
from studio_orchestrator import Instant, Job
from studio_quality import resolve_quality_rows
from studio_sql import SqlEngine
from studio_storage import ArtifactStore

from .scheduler_sql import SchedulerSqlResult, execute_scheduler_sql


class UnsupportedSchedulerWorkload(RuntimeError):
    """Raised when a scheduler workload has no qualified runtime adapter."""


class SchedulerWorkloadCancelled(RuntimeError):
    """Raised when a scheduler workload observes a durable cancellation request."""


@dataclass(frozen=True, slots=True)
class SchedulerWorkloadResult:
    family: str
    sql: SchedulerSqlResult | None = None
    graph: tuple[dict[str, object], ...] | None = None
    quality: dict[str, object] | None = None
    connector: dict[str, object] | None = None
    notification: dict[str, object] | None = None
    ml: dict[str, object] | None = None
    semantic: dict[str, object] | None = None
    pipeline: dict[str, object] | None = None

    def evidence_payload(self) -> dict[str, Any]:
        """Return the portable, deterministic payload stored as scheduler evidence."""

        if self.family == "sql" and self.sql is not None:
            return {
                "family": self.family,
                "evidence_digest": self.sql.evidence_digest,
                "columns": [
                    {"name": column.name, "type": column.type_name}
                    for column in self.sql.result.columns
                ],
                "rows": [list(row) for row in self.sql.result.rows],
                "version": 1,
            }
        if self.family == "graph" and self.graph is not None:
            return {
                "family": self.family,
                "objects": list(self.graph),
                "version": 1,
            }
        if self.family == "quality" and self.quality is not None:
            return {"family": self.family, "quality": self.quality, "version": 1}
        if self.family == "connector" and self.connector is not None:
            return {"family": self.family, "connector": self.connector, "version": 1}
        if self.family == "notification" and self.notification is not None:
            return {"family": self.family, "notification": self.notification, "version": 1}
        if self.family == "ml" and self.ml is not None:
            return {"family": self.family, "ml": self.ml, "version": 1}
        if self.family == "semantic" and self.semantic is not None:
            return {"family": self.family, "semantic": self.semantic, "version": 1}
        if self.family == "pipeline" and self.pipeline is not None:
            return {"family": self.family, "pipeline": self.pipeline, "version": 1}
        raise UnsupportedSchedulerWorkload("scheduler result has no portable evidence payload")


def execute_scheduler_job(
    job: Job,
    *,
    sql_engine: SqlEngine | None = None,
    graph_adapter: Any | None = None,
    quality_adapter: Any | None = None,
    artifact_store: ArtifactStore | None = None,
    workspace_id: Any | None = None,
    run_id: str | None = None,
    now: Any | None = None,
    connector_sync_service: Any | None = None,
    connector_connection: Any | None = None,
    connector_asset: Any | None = None,
    connector_secrets: Any | None = None,
    connector_destination: Any | None = None,
    cancellation_requested: Callable[[], bool] | None = None,
    notification_sink: Any | None = None,
    notification_artifacts: ArtifactStore | None = None,
    notification_now: Instant | str | None = None,
    ml_runner: Any | None = None,
    ml_lab: Any | None = None,
    ml_pipeline: Any | None = None,
    ml_rows: Any | None = None,
    semantic_refresh_runner: Any | None = None,
    pipeline_runner: Any | None = None,
    max_rows: int = 10_000,
    timeout_seconds: int | None = None,
) -> SchedulerWorkloadResult:
    """Dispatch a scheduler Job without falling back to notebook semantics."""

    if job.target == "sql.query":
        if sql_engine is None:
            raise UnsupportedSchedulerWorkload("sql.query requires an injected SQL engine")
        return SchedulerWorkloadResult(
            family="sql",
            sql=execute_scheduler_sql(
                job,
                sql_engine,
                max_rows=max_rows,
                timeout_seconds=timeout_seconds,
            ),
        )
    if job.target == "quality.gate":
        if (
            quality_adapter is None
            or artifact_store is None
            or workspace_id is None
            or run_id is None
        ):
            raise UnsupportedSchedulerWorkload(
                "quality.gate requires quality_adapter, artifact_store, workspace_id, and run_id"
            )
        quality_adapter = cast(Any, quality_adapter)
        try:
            payload = json.loads(job.parameters_json)
            asset_id = payload["asset_id"]
            version = payload["version"]
            contract_digest = payload["contract_digest"]
            rows_ref = payload["rows_ref"]
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise UnsupportedSchedulerWorkload("quality.gate parameters are invalid") from exc
        if (
            not all(
                isinstance(value, str) and value.strip() for value in (asset_id, version, rows_ref)
            )
            or not isinstance(contract_digest, str)
            or len(contract_digest) != 64
            or any(char not in "0123456789abcdef" for char in contract_digest)
        ):
            raise UnsupportedSchedulerWorkload("quality.gate parameters are invalid")
        rows = resolve_quality_rows(rows_ref, artifact_store)
        result = quality_adapter.run(
            workspace_id,
            {
                "asset": {"asset_id": asset_id, "version": version},
                "rows": list(rows),
                "run_id": run_id,
                "contract_digest": contract_digest,
                "execution_ref": rows_ref,
                "enforce_blocking": True,
            },
            now=now or job.updated_at,
        )
        if not isinstance(result, dict):
            raise UnsupportedSchedulerWorkload("quality adapter returned an invalid result")
        return SchedulerWorkloadResult(family="quality", quality=result)
    if job.target in {"connector.sync", "connector.sync.v1"}:
        if any(
            value is None
            for value in (
                connector_sync_service,
                connector_connection,
                connector_asset,
                connector_secrets,
                connector_destination,
                workspace_id,
            )
        ):
            raise UnsupportedSchedulerWorkload(
                "connector.sync requires service, workspace scope, source context, and destination"
            )
        if not isinstance(workspace_id, str) or not workspace_id.strip():
            raise UnsupportedSchedulerWorkload("connector.sync workspace scope is invalid")
        connector_sync_service = cast(Any, connector_sync_service)
        try:
            payload = json.loads(job.parameters_json)
            source_ref = payload["source_ref"]
            if not isinstance(source_ref, str) or source_ref.count("::") != 1:
                raise ValueError("source_ref must be connection_id::qualified_asset_name")
            connection_ref, asset_ref = source_ref.split("::", 1)
            if not connection_ref or not asset_ref:
                raise ValueError("source_ref must contain a connection and an asset")
            definition = IngestionSyncDefinition(
                id=payload["connector_id"],
                connector_id=payload["connector_id"],
                connection_ref=connection_ref,
                asset_ref=asset_ref,
                destination_ref=payload["destination_ref"],
                checkpoint_identity=payload["checkpoint_ref"],
                mode=payload.get("mode", "incremental"),
                source_revision_ref=(
                    AssetRef.from_payload(payload["source_revision_ref"])
                    if "source_revision_ref" in payload
                    else None
                ),
                destination_asset_id=(
                    AssetId(payload["destination_asset_id"])
                    if "destination_asset_id" in payload
                    else None
                ),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise UnsupportedSchedulerWorkload("connector.sync parameters are invalid") from exc
        connection = (
            connector_connection(workspace_id, definition.connection_ref)
            if callable(connector_connection)
            else connector_connection
        )
        asset = (
            connector_asset(connection, definition.asset_ref)
            if callable(connector_asset)
            else connector_asset
        )
        secrets = (
            connector_secrets(definition.connection_ref)
            if callable(connector_secrets)
            else connector_secrets
        )
        sync_options = (
            {"cancellation_requested": cancellation_requested}
            if cancellation_requested is not None
            else {}
        )
        try:
            result = connector_sync_service.execute(
                definition,
                workspace_id=workspace_id,
                connection=connection,
                asset=asset,
                secrets=secrets,
                destination=connector_destination,
                execution_ref=run_id,
                now=None if now is None else str(now),
                **sync_options,
            )
        except IngestionSyncCancelled as exc:
            raise SchedulerWorkloadCancelled(str(exc)) from exc
        if not isinstance(result, dict):
            raise UnsupportedSchedulerWorkload("connector sync returned an invalid result")
        return SchedulerWorkloadResult(family="connector", connector=result)
    if job.target == "notification.send":
        if notification_sink is None or notification_artifacts is None:
            raise UnsupportedSchedulerWorkload(
                "notification.send requires notification_sink and notification_artifacts"
            )
        try:
            payload = json.loads(job.parameters_json)
            notification_id = payload["notification_id"]
            channel = payload["channel"]
            destination_ref = payload["destination_ref"]
            payload_ref = payload["payload_ref"]
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise UnsupportedSchedulerWorkload("notification.send parameters are invalid") from exc
        if (
            channel not in {"smtp", "webhook"}
            or not isinstance(destination_ref, str)
            or not destination_ref.strip()
        ):
            raise UnsupportedSchedulerWorkload("notification.send destination is invalid")
        from studio_quality.artifact_rows import _REF  # noqa: PLC0415

        match = _REF.fullmatch(payload_ref) if isinstance(payload_ref, str) else None
        getter = getattr(notification_artifacts, "get_bytes_by_storage_ref", None)
        if match is None or getter is None:
            raise UnsupportedSchedulerWorkload("notification payload must be a verified artifact")
        try:
            body = json.loads(getter(payload_ref, digest=match.group(1)))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise UnsupportedSchedulerWorkload("notification payload artifact is invalid") from exc
        if not isinstance(body, dict) or not all(
            isinstance(body.get(key), str) and body[key].strip()
            for key in ("kind", "title", "body")
        ):
            raise UnsupportedSchedulerWorkload(
                "notification payload requires kind, title, and body"
            )
        intent = NotificationIntent(
            notification_id,
            body["kind"],
            body["title"],
            body["body"],
            Instant(notification_now or job.updated_at),
            (("channel", channel), ("destination_ref", destination_ref)),
        )
        delivery_id = notification_sink.send(intent)
        if delivery_id != intent.id:
            raise UnsupportedSchedulerWorkload("notification sink returned a different intent id")
        return SchedulerWorkloadResult(
            family="notification",
            notification={"notification_id": intent.id, "delivery_id": delivery_id},
        )
    if job.target == "ml.run":
        if ml_runner is None or ml_lab is None or ml_pipeline is None or ml_rows is None:
            raise UnsupportedSchedulerWorkload("ml.run requires runner, lab, pipeline, and rows")
        try:
            payload = json.loads(job.parameters_json)
            lab_id = payload["lab_id"]
            dataset_ref = payload["dataset_ref"]
            pipeline_digest = payload["pipeline_digest"]
            if not all(isinstance(value, str) and value.strip() for value in (lab_id, dataset_ref)):
                raise ValueError("missing ML identifiers")
            if (
                not isinstance(pipeline_digest, str)
                or len(pipeline_digest) != 64
                or any(char not in "0123456789abcdef" for char in pipeline_digest)
            ):
                raise ValueError("invalid ML pipeline digest")
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise UnsupportedSchedulerWorkload("ml.run parameters are invalid") from exc
        if getattr(ml_lab, "id", None) != lab_id:
            raise UnsupportedSchedulerWorkload("ml.run lab does not match the planned lab id")
        lab_digest = getattr(ml_lab, "digest", None)
        pipeline_parameters = getattr(ml_pipeline, "parameters", None)
        if not isinstance(pipeline_parameters, tuple):
            raise UnsupportedSchedulerWorkload(
                "ml.run pipeline does not pin the current lab definition"
            )
        try:
            pinned_lab_digest = dict(pipeline_parameters)["lab_digest"]
        except (KeyError, TypeError, ValueError) as exc:
            raise UnsupportedSchedulerWorkload(
                "ml.run pipeline does not pin the current lab definition"
            ) from exc
        if not isinstance(lab_digest, str) or pinned_lab_digest != lab_digest:
            raise UnsupportedSchedulerWorkload(
                "ml.run pipeline does not pin the current lab definition"
            )
        if getattr(ml_pipeline, "digest", None) != pipeline_digest:
            raise UnsupportedSchedulerWorkload(
                "ml.run pipeline digest does not match the planned pipeline"
            )
        execute_pipeline = getattr(ml_runner, "execute_pipeline", None)
        if not callable(execute_pipeline):
            raise UnsupportedSchedulerWorkload(
                "ML runner cannot execute the planned pipeline definition"
            )
        result = execute_pipeline(ml_lab, ml_rows, ml_pipeline)
        to_payload = getattr(result, "to_payload", None)
        if not callable(to_payload):
            raise UnsupportedSchedulerWorkload("ML runner returned an invalid result")
        ml_result = to_payload()
        if not isinstance(ml_result, dict):
            raise UnsupportedSchedulerWorkload("ML runner returned an invalid result")
        return SchedulerWorkloadResult(
            family="ml", ml={**ml_result, "pipeline_digest": pipeline_digest}
        )
    if job.target == "semantic.refresh":
        if semantic_refresh_runner is None:
            raise UnsupportedSchedulerWorkload(
                "semantic.refresh requires an injected semantic_refresh_runner"
            )
        try:
            payload = json.loads(job.parameters_json)
            model_id = payload["model_id"]
            definition_digest = payload["definition_digest"]
            tile_limit = payload.get("tile_limit", 100)
            if (
                not isinstance(model_id, str)
                or not model_id.strip()
                or not isinstance(definition_digest, str)
                or len(definition_digest) != 64
                or any(char not in "0123456789abcdef" for char in definition_digest)
                or isinstance(tile_limit, bool)
                or not isinstance(tile_limit, int)
                or not 1 <= tile_limit <= 10_000
            ):
                raise ValueError("invalid semantic refresh identifiers")
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise UnsupportedSchedulerWorkload("semantic.refresh parameters are invalid") from exc
        result = semantic_refresh_runner.run(
            model_id=model_id,
            definition_digest=definition_digest,
            tile_limit=tile_limit,
        )
        if not isinstance(result, dict):
            raise UnsupportedSchedulerWorkload("semantic refresh runner returned an invalid result")
        return SchedulerWorkloadResult(family="semantic", semantic=result)
    if job.target == "data-engineering.pipeline-run.v1":
        if pipeline_runner is None:
            raise UnsupportedSchedulerWorkload(
                "data-engineering.pipeline-run.v1 requires an injected pipeline_runner"
            )
        try:
            payload = json.loads(job.parameters_json)
            revision_key = payload["revision_key"]
            ir_digest = payload["ir_digest"]
            runtime = payload["runtime"]
            parameters = payload.get("parameters", {})
            if (
                not isinstance(revision_key, str)
                or not revision_key.strip()
                or not isinstance(ir_digest, str)
                or len(ir_digest) != 64
                or any(char not in "0123456789abcdef" for char in ir_digest)
                or not isinstance(runtime, str)
                or not runtime.strip()
                or not isinstance(parameters, dict)
            ):
                raise ValueError("invalid pipeline execution identity")
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise UnsupportedSchedulerWorkload(
                "data-engineering.pipeline-run.v1 parameters are invalid"
            ) from exc
        result = pipeline_runner.run(
            revision_key=revision_key,
            ir_digest=ir_digest,
            runtime=runtime,
            parameters=parameters,
        )
        if not isinstance(result, dict):
            raise UnsupportedSchedulerWorkload("pipeline runner returned an invalid result")
        return SchedulerWorkloadResult(family="pipeline", pipeline=result)
    if job.target == "graph.query":
        if graph_adapter is None:
            raise UnsupportedSchedulerWorkload("graph.query requires an injected graph adapter")
        try:
            payload = json.loads(job.parameters_json)
            graph_id = payload["graph_id"]
            query = payload["query"]
            limit = payload.get("limit", 100)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise UnsupportedSchedulerWorkload("graph.query parameters are invalid") from exc
        if (
            not isinstance(graph_id, str)
            or not graph_id.strip()
            or not isinstance(query, str)
            or not query.strip()
            or isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 10_000
        ):
            raise UnsupportedSchedulerWorkload("graph.query parameters are invalid")
        try:
            objects = tuple(graph_adapter.query(graph_id, query, max_limit=limit).objects)
        except (AttributeError, TypeError, ValueError) as exc:
            raise UnsupportedSchedulerWorkload(
                "graph.query adapter returned an invalid result"
            ) from exc
        if len(objects) > limit:
            raise UnsupportedSchedulerWorkload("graph.query adapter exceeded max_limit")
        return SchedulerWorkloadResult(
            family="graph",
            graph=tuple(
                {
                    "object_type": item.ref.object_type,
                    "key": [[name, value] for name, value in item.ref.key],
                    "properties": [[name, value] for name, value in item.properties],
                }
                for item in objects
            ),
        )
    raise UnsupportedSchedulerWorkload(f"no qualified scheduler adapter for {job.target}")


__all__ = ("SchedulerWorkloadResult", "UnsupportedSchedulerWorkload", "execute_scheduler_job")
