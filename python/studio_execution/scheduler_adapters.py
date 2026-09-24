"""Explicit dispatch boundary for scheduler workload families."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from studio_connectors import IngestionSyncDefinition
from studio_observability import NotificationIntent
from studio_orchestrator import Instant, Job
from studio_quality import resolve_quality_rows
from studio_sql import SqlEngine
from studio_storage import ArtifactStore

from .scheduler_sql import SchedulerSqlResult, execute_scheduler_sql


class UnsupportedSchedulerWorkload(RuntimeError):
    """Raised when a scheduler workload has no qualified runtime adapter."""


@dataclass(frozen=True, slots=True)
class SchedulerWorkloadResult:
    family: str
    sql: SchedulerSqlResult | None = None
    graph: tuple[dict[str, object], ...] | None = None
    quality: dict[str, object] | None = None
    connector: dict[str, object] | None = None
    notification: dict[str, object] | None = None
    ml: dict[str, object] | None = None
    genai: dict[str, object] | None = None
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
        if self.family == "genai" and self.genai is not None:
            return {"family": self.family, "genai": self.genai, "version": 1}
        if self.family == "semantic" and self.semantic is not None:
            return {"family": self.family, "semantic": self.semantic, "version": 1}
        if self.family == "pipeline" and self.pipeline is not None:
            return {"family": self.family, "pipeline": self.pipeline, "version": 1}
        raise UnsupportedSchedulerWorkload("scheduler result has no portable evidence payload")


def execute_scheduler_job(
    job: Job,
    *,
    sql_engine: SqlEngine | None = None,
    graph_adapter: object | None = None,
    quality_adapter: object | None = None,
    artifact_store: ArtifactStore | None = None,
    workspace_id: object | None = None,
    run_id: str | None = None,
    now: object | None = None,
    connector_sync_service: object | None = None,
    connector_connection: object | None = None,
    connector_asset: object | None = None,
    connector_secrets: object | None = None,
    connector_destination: object | None = None,
    notification_sink: object | None = None,
    notification_artifacts: ArtifactStore | None = None,
    notification_now: Instant | str | None = None,
    ml_runner: object | None = None,
    ml_lab: object | None = None,
    ml_rows: object | None = None,
    genai_runner: object | None = None,
    semantic_refresh_runner: object | None = None,
    pipeline_runner: object | None = None,
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
                "execution_ref": rows_ref,
                "enforce_blocking": True,
            },
            now=now or job.updated_at,
        )
        if not isinstance(result, dict):
            raise UnsupportedSchedulerWorkload("quality adapter returned an invalid result")
        return SchedulerWorkloadResult(family="quality", quality=result)
    if job.target == "connector.sync":
        if any(
            value is None
            for value in (
                connector_sync_service,
                connector_connection,
                connector_asset,
                connector_secrets,
                connector_destination,
            )
        ):
            raise UnsupportedSchedulerWorkload(
                "connector.sync requires service, source context, and destination"
            )
        try:
            payload = json.loads(job.parameters_json)
            definition = IngestionSyncDefinition(
                id=payload["connector_id"],
                connector_id=payload["connector_id"],
                connection_ref=payload["source_ref"],
                asset_ref=payload["source_ref"],
                destination_ref=payload["destination_ref"],
                checkpoint_identity=payload["checkpoint_ref"],
                mode=payload.get("mode", "incremental"),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise UnsupportedSchedulerWorkload("connector.sync parameters are invalid") from exc
        result = connector_sync_service.execute(
            definition,
            connection=connector_connection,
            asset=connector_asset,
            secrets=connector_secrets,
            destination=connector_destination,
        )
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
        if channel not in {"smtp", "webhook"} or not isinstance(destination_ref, str):
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
        if ml_runner is None or ml_lab is None or ml_rows is None:
            raise UnsupportedSchedulerWorkload("ml.run requires runner, lab, and rows")
        try:
            payload = json.loads(job.parameters_json)
            if not all(isinstance(payload.get(key), str) for key in ("lab_id", "dataset_ref")):
                raise ValueError("missing ML identifiers")
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise UnsupportedSchedulerWorkload("ml.run parameters are invalid") from exc
        result = ml_runner.run(ml_lab, ml_rows)
        to_payload = getattr(result, "to_payload", None)
        if not callable(to_payload):
            raise UnsupportedSchedulerWorkload("ML runner returned an invalid result")
        return SchedulerWorkloadResult(family="ml", ml=to_payload())
    if job.target == "genai.run":
        if genai_runner is None:
            raise UnsupportedSchedulerWorkload("genai.run requires an injected genai_runner")
        try:
            payload = json.loads(job.parameters_json)
            required = ("provider_id", "model_id", "prompt_ref")
            if not all(
                isinstance(payload.get(key), str) and payload[key].strip() for key in required
            ):
                raise ValueError("missing GenAI identifiers")
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise UnsupportedSchedulerWorkload("genai.run parameters are invalid") from exc
        result = genai_runner.run(payload)
        if not isinstance(result, dict):
            raise UnsupportedSchedulerWorkload("GenAI runner returned an invalid result")
        return SchedulerWorkloadResult(family="genai", genai=result)
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
        if not isinstance(graph_id, str) or not isinstance(query, str):
            raise UnsupportedSchedulerWorkload("graph.query requires graph_id and query")
        objects = graph_adapter.query(graph_id, query, max_limit=limit).objects
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
