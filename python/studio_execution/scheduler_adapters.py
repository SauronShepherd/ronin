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
