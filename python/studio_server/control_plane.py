"""Authenticated HTTP surface for provider-neutral workspace/project services."""

from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import tempfile
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Protocol, TypeVar, cast, runtime_checkable
from urllib.parse import parse_qs, unquote, urlsplit

from studio_core import (
    AssetId,
    AssetRef,
    AssetRevision,
    AssetVersion,
    CatalogAsset,
    GlossaryTerm,
    GlossaryTermId,
    KnowledgeObject,
    LineageEdge,
    OntologyDefinition,
    OntologyId,
    OwnershipMetadata,
    Pipeline,
    ProjectId,
    ProjectManifest,
    RqlResult,
    Schedule,
    ScheduleId,
    SensitivityMetadata,
    TaskRun,
    Trigger,
    WorkflowDefinition,
    WorkflowId,
    WorkflowRun,
    WorkflowRunId,
    Workspace,
    WorkspaceId,
)
from studio_core.canonical_json import decode as decode_canonical_json
from studio_core.environments import (
    EnvironmentDefinition,
    EnvironmentId,
    ProjectEnvironmentBindings,
)
from studio_core.ontology import KnowledgeObjectRef
from studio_core.scheduler_events import EventTriggerDefinition, SchedulerEventId
from studio_data_engineering import PipelineRevisionRecord, SdpProjectSource
from studio_execution import (
    DeploymentBindingService,
    EnvironmentService,
    EnvironmentServiceConflict,
    EnvironmentServiceNotFound,
    ProjectService,
    WorkspaceService,
    WorkspaceServiceConflict,
    WorkspaceServiceNotFound,
    diff_environments,
)
from studio_orchestrator import Instant
from studio_quality.http import QualityHTTPAdapter
from studio_security import Actor, Permission, PolicyDecision, PolicyRequirement
from studio_storage.bundle import BundleFile, write_bundle
from studio_storage.bundle_payload import read_bundle_payload
from studio_storage.scheduler_backfill import BackfillId, BackfillRequest
from studio_storage.scheduler_events import EventDelivery, SchedulerEventRecord
from studio_storage.scheduler_schedule import ScheduleFire

_MAX_REQUEST_BYTES = 1024 * 1024
_MAX_LIST_LIMIT = 100
_DEFAULT_LIST_LIMIT = 50
_MAX_CURSOR_BYTES = 256

CONTROL_PLANE_ROUTES = frozenset(
    {
        ("GET", "/v1/platform/plugins"),
        ("GET", "/v1/platform/capabilities"),
        ("GET", "/v1/platform/connectors"),
        ("POST", "/v1/platform/connectors/preview"),
        ("POST", "/v1/platform/connectors/plan"),
        ("POST", "/v1/platform/connectors/checkpoint-health"),
        ("GET", "/v1/platform/ui-manifest"),
        ("GET", "/v1/platform/logs"),
        ("GET", "/v1/platform/traces"),
        ("GET", "/v1/platform/metrics"),
        ("GET", "/v1/workspaces"),
        ("POST", "/v1/workspaces"),
        ("GET", "/v1/workspaces/{workspace_id}"),
        ("PATCH", "/v1/workspaces/{workspace_id}"),
        ("POST", "/v1/workspaces/{workspace_id}/archive"),
        ("GET", "/v1/workspaces/{workspace_id}/projects"),
        ("POST", "/v1/workspaces/{workspace_id}/projects"),
        ("GET", "/v1/workspaces/{workspace_id}/projects/{project_id}"),
        ("GET", "/v1/workspaces/{workspace_id}/projects/{project_id}/permissions"),
        ("GET", "/v1/workspaces/{workspace_id}/quality/contracts/{asset_id}/{version}"),
        ("POST", "/v1/workspaces/{workspace_id}/quality/runs"),
        ("GET", "/v1/workspaces/{workspace_id}/quality/runs/{asset_id}/{version}"),
        ("GET", "/v1/workspaces/{workspace_id}/quality/state/{asset_id}/{version}"),
        ("GET", "/v1/workspaces/{workspace_id}/alerts/rules"),
        ("GET", "/v1/workspaces/{workspace_id}/alerts/instances"),
        ("POST", "/v1/workspaces/{workspace_id}/alerts/evaluate"),
        ("POST", "/v1/workspaces/{workspace_id}/alerts/acknowledge"),
        ("GET", "/v1/workspaces/{workspace_id}/finops/usage"),
        ("GET", "/v1/workspaces/{workspace_id}/finops/costs"),
        ("GET", "/v1/workspaces/{workspace_id}/finops/budgets"),
        ("GET", "/v1/workspaces/{workspace_id}/environments"),
        ("POST", "/v1/workspaces/{workspace_id}/environments"),
        ("GET", "/v1/workspaces/{workspace_id}/environments/{environment_id}"),
        ("PUT", "/v1/workspaces/{workspace_id}/environments/{environment_id}"),
        ("POST", "/v1/workspaces/{workspace_id}/environments/{environment_id}/diff"),
        ("POST", "/v1/workspaces/{workspace_id}/environments/{environment_id}/disable"),
        ("POST", "/v1/workspaces/{workspace_id}/environments/{environment_id}/enable"),
        (
            "GET",
            "/v1/workspaces/{workspace_id}/projects/{project_id}/environments/{environment_id}/bindings",
        ),
        (
            "PUT",
            "/v1/workspaces/{workspace_id}/projects/{project_id}/environments/{environment_id}/bindings",
        ),
        ("PUT", "/v1/workspaces/{workspace_id}/projects/{project_id}"),
        ("GET", "/v1/workspaces/{workspace_id}/projects/{project_id}/bundle"),
        ("GET", "/v1/workspaces/{workspace_id}/projects/{project_id}/bundle/archive"),
        ("POST", "/v1/workspaces/{workspace_id}/projects/{project_id}/bundle/import"),
        ("DELETE", "/v1/workspaces/{workspace_id}/projects/{project_id}"),
        ("POST", "/v1/workspaces/{workspace_id}/projects/{project_id}/archive"),
        (
            "GET",
            "/v1/workspaces/{workspace_id}/projects/{project_id}/pipelines",
        ),
        (
            "GET",
            "/v1/workspaces/{workspace_id}/projects/{project_id}/pipelines/{pipeline_id}/revisions",
        ),
        (
            "GET",
            "/v1/workspaces/{workspace_id}/projects/{project_id}/pipelines/{pipeline_id}/revisions/{revision}",
        ),
        (
            "GET",
            "/v1/workspaces/{workspace_id}/projects/{project_id}/pipelines/{pipeline_id}/revisions/compare",
        ),
        (
            "POST",
            "/v1/workspaces/{workspace_id}/projects/{project_id}/pipelines/{pipeline_id}/archive",
        ),
        (
            "POST",
            "/v1/workspaces/{workspace_id}/projects/{project_id}/pipelines/{pipeline_id}/runs",
        ),
        (
            "POST",
            "/v1/workspaces/{workspace_id}/projects/{project_id}/pipelines/{pipeline_id}/revisions",
        ),
        ("GET", "/v1/workspaces/{workspace_id}/projects/{project_id}/notebooks"),
        ("GET", "/v1/workspaces/{workspace_id}/projects/{project_id}/notebooks/{notebook_id}"),
        ("POST", "/v1/workspaces/{workspace_id}/projects/{project_id}/notebooks"),
        ("PUT", "/v1/workspaces/{workspace_id}/projects/{project_id}/notebooks/{notebook_id}"),
        (
            "POST",
            "/v1/workspaces/{workspace_id}/projects/{project_id}/notebooks/{notebook_id}/archive",
        ),
        ("DELETE", "/v1/workspaces/{workspace_id}/projects/{project_id}/notebooks/{notebook_id}"),
        ("GET", "/v1/workspaces/{workspace_id}/workflows"),
        ("GET", "/v1/workspaces/{workspace_id}/schedules"),
        ("GET", "/v1/workspaces/{workspace_id}/schedules/{schedule_id}"),
        ("GET", "/v1/workspaces/{workspace_id}/schedules/{schedule_id}/next-runs"),
        ("GET", "/v1/workspaces/{workspace_id}/schedules/{schedule_id}/history"),
        ("PUT", "/v1/workspaces/{workspace_id}/schedules/{schedule_id}"),
        ("GET", "/v1/workspaces/{workspace_id}/event-triggers"),
        ("GET", "/v1/workspaces/{workspace_id}/event-deliveries"),
        ("PUT", "/v1/workspaces/{workspace_id}/event-triggers/{trigger_id}"),
        ("POST", "/v1/workspaces/{workspace_id}/events"),
        ("POST", "/v1/workspaces/{workspace_id}/backfills"),
        ("POST", "/v1/workspaces/{workspace_id}/backfills/preview"),
        ("GET", "/v1/workspaces/{workspace_id}/backfills/{backfill_id}"),
        ("POST", "/v1/workspaces/{workspace_id}/backfills/{backfill_id}/cancel"),
        ("POST", "/v1/workspaces/{workspace_id}/graphs/{graph_id}/query"),
        ("GET", "/v1/workspaces/{workspace_id}/graphs/{graph_id}/objects/{object_type}"),
        ("POST", "/v1/workspaces/{workspace_id}/graphs/{graph_id}/neighbors"),
        ("POST", "/v1/workspaces/{workspace_id}/graphs/{graph_id}/actions"),
        ("GET", "/v1/workspaces/{workspace_id}/ontologies/{ontology_id}"),
        ("GET", "/v1/workspaces/{workspace_id}/ontologies/{ontology_id}/{version}"),
        ("GET", "/v1/workspaces/{workspace_id}/catalog/assets"),
        ("GET", "/v1/workspaces/{workspace_id}/catalog/assets/{asset_id}/revisions"),
        ("GET", "/v1/workspaces/{workspace_id}/catalog/lineage/{asset_id}/{version}"),
        (
            "GET",
            "/v1/workspaces/{workspace_id}/catalog/assets/{asset_id}/revisions/{version}",
        ),
        ("POST", "/v1/workspaces/{workspace_id}/catalog/assets"),
        ("PUT", "/v1/workspaces/{workspace_id}/catalog/assets/{asset_id}"),
        ("POST", "/v1/workspaces/{workspace_id}/catalog/assets/{asset_id}/sensitivity"),
        ("POST", "/v1/workspaces/{workspace_id}/catalog/assets/{asset_id}/ownership"),
        ("GET", "/v1/workspaces/{workspace_id}/glossary/terms"),
        ("POST", "/v1/workspaces/{workspace_id}/glossary/terms"),
        ("GET", "/v1/workspaces/{workspace_id}/glossary/terms/{term_id}/{version}"),
        ("GET", "/v1/workspaces/{workspace_id}/streams/{stream_id}/health"),
        ("GET", "/v1/workspaces/{workspace_id}/projects/{project_id}/semantic/models"),
        ("POST", "/v1/workspaces/{workspace_id}/projects/{project_id}/semantic/query"),
        ("POST", "/v1/workspaces/{workspace_id}/projects/{project_id}/sql/query"),
        ("POST", "/v1/workspaces/{workspace_id}/projects/{project_id}/semantic/join"),
        ("GET", "/v1/workspaces/{workspace_id}/projects/{project_id}/semantic/dashboards"),
        (
            "GET",
            "/v1/workspaces/{workspace_id}/projects/{project_id}/semantic/dashboards/{dashboard_id}",
        ),
        (
            "PUT",
            "/v1/workspaces/{workspace_id}/projects/{project_id}/semantic/dashboards/{dashboard_id}",
        ),
        (
            "POST",
            "/v1/workspaces/{workspace_id}/projects/{project_id}/semantic/dashboards/{dashboard_id}/execute",
        ),
        ("POST", "/v1/workspaces/{workspace_id}/workflows/{workflow_id}/runs"),
        ("GET", "/v1/workspaces/{workspace_id}/workflow-runs/{run_id}"),
        ("POST", "/v1/workspaces/{workspace_id}/workflow-runs/{run_id}/cancel"),
        ("GET", "/v1/ml-studio/labs"),
        ("POST", "/v1/ml-studio/labs"),
        ("GET", "/v1/ml-studio/features"),
        ("POST", "/v1/ml-studio/features"),
        ("GET", "/v1/ml-studio/features/{feature_id}/{version}"),
        ("POST", "/v1/ml-studio/labs/{lab_id}/quality"),
        ("POST", "/v1/ml-studio/labs/{lab_id}/executions"),
        ("POST", "/v1/ml-studio/labs/{lab_id}/compare"),
        ("POST", "/v1/ml-studio/labs/{lab_id}/search"),
        ("GET", "/v1/ml-studio/models"),
        ("POST", "/v1/ml-studio/models/{model_id}/{version}/promote"),
        ("POST", "/v1/ml-studio/models/{model_id}/{version}/predict"),
        ("POST", "/v1/ml-studio/models/{model_id}/{version}/batch-predict"),
        ("GET", "/v1/ml-studio/models/{model_id}/{version}/card"),
    }
)


def _registered_path_matches(route: str, segments: tuple[str, ...]) -> bool:
    pattern = tuple(part for part in route.removeprefix("/").split("/") if part)
    return len(pattern) == len(segments) and all(
        expected.startswith("{") and expected.endswith("}") or expected == actual
        for expected, actual in zip(pattern, segments, strict=True)
    )


class ControlPlaneUnavailable(RuntimeError):
    """Raised by auth/authz adapters when a required dependency is unavailable."""


@runtime_checkable
class ControlPlaneAuthenticator(Protocol):
    def authenticate(self, authorization: str | None) -> Actor | None: ...


@runtime_checkable
class ControlPlaneAuthorizer(Protocol):
    def authorize(self, actor: Actor, requirement: PolicyRequirement) -> PolicyDecision: ...


ControlPlaneAuditHook = Callable[[Actor, str, WorkspaceId, dict[str, object]], None]


@runtime_checkable
class WorkflowReader(Protocol):
    def list_workflows(self, workspace_id: WorkspaceId) -> tuple[WorkflowDefinition, ...]: ...

    def list_schedules(self, workspace_id: WorkspaceId) -> tuple[Schedule, ...]: ...

    def get_schedule(
        self, workspace_id: WorkspaceId, schedule_id: ScheduleId
    ) -> Schedule | None: ...

    def preview_schedule_next_runs(
        self,
        workspace_id: WorkspaceId,
        schedule_id: ScheduleId,
        *,
        after: Instant | str,
        count: int = 10,
    ) -> tuple[Instant, ...]: ...

    def list_schedule_fires(
        self, workspace_id: WorkspaceId, schedule_id: ScheduleId
    ) -> tuple[ScheduleFire, ...]: ...

    def list_pending_deliveries(
        self, workspace_id: WorkspaceId, *, limit: int = 100
    ) -> tuple[EventDelivery, ...]: ...

    def preview_backfill(
        self,
        workspace_id: WorkspaceId,
        schedule_id: ScheduleId,
        *,
        start_at: Instant | str,
        end_at: Instant | str,
        max_runs: int = 1000,
    ) -> tuple[Instant, ...]: ...

    def put_schedule(self, workspace_id: WorkspaceId, schedule: Schedule) -> Schedule: ...

    def list_event_triggers(
        self, workspace_id: WorkspaceId
    ) -> tuple[EventTriggerDefinition, ...]: ...

    def put_event_trigger(
        self, workspace_id: WorkspaceId, trigger: EventTriggerDefinition
    ) -> EventTriggerDefinition: ...

    def ingest_event(self, event: SchedulerEventRecord) -> tuple[EventDelivery, ...]: ...

    def create_backfill(
        self, workspace_id: WorkspaceId, request: BackfillRequest
    ) -> BackfillRequest: ...

    def get_backfill(
        self, workspace_id: WorkspaceId, backfill_id: BackfillId
    ) -> BackfillRequest | None: ...

    def cancel_backfill(
        self, workspace_id: WorkspaceId, backfill_id: BackfillId
    ) -> BackfillRequest: ...

    def get_run(self, workspace_id: WorkspaceId, run_id: WorkflowRunId) -> WorkflowRun | None: ...

    def list_task_runs(
        self, workspace_id: WorkspaceId, run_id: WorkflowRunId
    ) -> tuple[TaskRun, ...]: ...


@runtime_checkable
class WorkflowCanceller(Protocol):
    def cancel_workflow_run(self, workspace_id: WorkspaceId, run_id: WorkflowRunId) -> int: ...


@runtime_checkable
class GraphQueryReader(Protocol):
    def query(self, graph_id: str, query: str, *, max_limit: int = 1000) -> RqlResult: ...

    def list_objects(
        self, graph_id: str, object_type: str, *, limit: int = 100
    ) -> tuple[KnowledgeObject, ...]: ...

    def neighbors(
        self, graph_id: str, ref: KnowledgeObjectRef, *, limit: int = 100
    ) -> tuple[KnowledgeObjectRef, ...]: ...


class GraphActionReader(Protocol):
    def execute_action_payload(self, graph_id: str, payload: dict[str, object]) -> object: ...


class OntologyReader(Protocol):
    def list_schema_versions(
        self, workspace_id: WorkspaceId, ontology_id: OntologyId
    ) -> tuple[OntologyDefinition, ...]: ...

    def get_schema(
        self, workspace_id: WorkspaceId, ontology_id: OntologyId, version: str
    ) -> OntologyDefinition | None: ...


@runtime_checkable
class CatalogReader(Protocol):
    def list_assets(self, workspace_id: WorkspaceId) -> tuple[CatalogAsset, ...]: ...

    def search_assets(
        self, workspace_id: WorkspaceId, query: str, *, limit: int = 100
    ) -> tuple[CatalogAsset, ...]: ...

    def create_asset(
        self, workspace_id: WorkspaceId, asset: CatalogAsset, *, now: Instant
    ) -> CatalogAsset: ...

    def replace_asset(
        self, workspace_id: WorkspaceId, asset: CatalogAsset, *, now: Instant
    ) -> CatalogAsset: ...

    def list_revisions(
        self, workspace_id: WorkspaceId, asset_id: AssetId
    ) -> tuple[AssetRevision, ...]: ...

    def get_revision(self, workspace_id: WorkspaceId, ref: AssetRef) -> AssetRevision | None: ...

    def upstream(self, workspace_id: WorkspaceId, ref: AssetRef) -> tuple[LineageEdge, ...]: ...

    def downstream(self, workspace_id: WorkspaceId, ref: AssetRef) -> tuple[LineageEdge, ...]: ...

    def list_lineage(
        self, workspace_id: WorkspaceId, *, limit: int = 1000
    ) -> tuple[LineageEdge, ...]: ...

    def put_sensitivity(
        self,
        workspace_id: WorkspaceId,
        asset_id: AssetId,
        metadata: SensitivityMetadata,
        *,
        now: Instant,
    ) -> object: ...

    def put_ownership(
        self,
        workspace_id: WorkspaceId,
        asset_id: AssetId,
        metadata: OwnershipMetadata,
        *,
        now: Instant,
    ) -> object: ...


@runtime_checkable
class DataEngineeringRevisionReader(Protocol):
    def list_pipelines(self, *, project_id: str) -> tuple[str, ...]: ...

    def list_revisions(
        self, *, project_id: str, pipeline_id: str
    ) -> tuple[dict[str, object], ...]: ...

    def get_revision(
        self, *, project_id: str, pipeline_id: str, revision: int
    ) -> dict[str, object] | None: ...

    def compare(
        self, *, project_id: str, pipeline_id: str, left_revision: int, right_revision: int
    ) -> dict[str, object]: ...

    def archive(self, *, project_id: str, pipeline_id: str) -> bool: ...

    def import_sdp(
        self,
        *,
        project_id: str,
        pipeline_id: str,
        source: SdpProjectSource,
        expected_revision: int | None = None,
    ) -> PipelineRevisionRecord: ...


@runtime_checkable
class NotebookReader(Protocol):
    def list(self, *, project_id: str, include_archived: bool = False) -> object: ...
    def get(self, *, project_id: str, notebook_id: str) -> object: ...
    def create(self, *, project_id: str, payload: dict[str, object]) -> object: ...
    def save(self, *, project_id: str, notebook_id: str, payload: dict[str, object]) -> object: ...
    def archive(self, *, project_id: str, notebook_id: str, expected_revision: int) -> object: ...
    def delete(self, *, project_id: str, notebook_id: str, expected_revision: int) -> object: ...


@runtime_checkable
class GlossaryReader(Protocol):
    def list_all(self, workspace_id: WorkspaceId) -> tuple[GlossaryTerm, ...]: ...

    def list_latest(self, workspace_id: WorkspaceId) -> tuple[GlossaryTerm, ...]: ...

    def search(
        self, workspace_id: WorkspaceId, query: str, *, limit: int = 100
    ) -> tuple[GlossaryTerm, ...]: ...

    def get(
        self, workspace_id: WorkspaceId, term_id: GlossaryTermId, version: str
    ) -> GlossaryTerm | None: ...

    def put(
        self, workspace_id: WorkspaceId, term: GlossaryTerm, *, now: Instant
    ) -> GlossaryTerm: ...


@runtime_checkable
class StreamingHealthReader(Protocol):
    def health(self, workspace_id: WorkspaceId, stream_id: str) -> dict[str, object]: ...


@runtime_checkable
class FinOpsReader(Protocol):
    def list_usage(
        self, workspace_id: WorkspaceId, *, period_start: str, period_end: str
    ) -> object: ...
    def list_costs(
        self, workspace_id: WorkspaceId, *, period_start: str, period_end: str
    ) -> object: ...
    def list_budgets(self, workspace_id: WorkspaceId) -> object: ...


@runtime_checkable
class AlertReader(Protocol):
    def list_rules(self) -> dict[str, object]: ...

    def list_instances(self, *, limit: int = 100) -> dict[str, object]: ...

    def evaluate(self, body: object, *, now: Instant | str) -> dict[str, object]: ...

    def acknowledge(self, body: object, *, now: Instant | str) -> dict[str, object]: ...


@runtime_checkable
class SemanticReader(Protocol):
    def list_models(self, project_id: str) -> dict[str, object]: ...

    def list_dashboards(self, project_id: str) -> dict[str, object]: ...

    def get_dashboard(self, project_id: str, dashboard_id: str) -> dict[str, object] | None: ...

    def query(self, project_id: str, body: object) -> dict[str, object]: ...

    def join_query(self, project_id: str, body: object) -> dict[str, object]: ...

    def put_dashboard(self, project_id: str, body: object) -> dict[str, object]: ...

    def execute_dashboard(self, project_id: str, dashboard_id: str) -> dict[str, object]: ...


@runtime_checkable
class SqlReader(Protocol):
    def query(self, project_id: str, body: object) -> dict[str, object]: ...


@runtime_checkable
class WorkflowRunner(Protocol):
    def put_workflow(
        self, workspace_id: WorkspaceId, workflow: WorkflowDefinition
    ) -> WorkflowDefinition: ...

    def create_workflow_run(
        self,
        workspace_id: WorkspaceId,
        workflow_id: WorkflowId,
        trigger: Trigger,
        *,
        idempotency_key: str,
    ) -> WorkflowRun: ...


@runtime_checkable
class PluginDiagnostics(Protocol):
    def diagnostics(self) -> tuple[dict[str, str | None], ...]: ...

    def contribution_diagnostics(self) -> dict[str, object]: ...


@runtime_checkable
class PluginRouter(Protocol):
    def resolve_route(self, method: str, path: str) -> tuple[object, dict[str, str]] | None: ...

    def invoke_route(
        self,
        method: str,
        path: str,
        *,
        query: str | None = None,
        body: object | None = None,
        idempotency_key: str | None = None,
    ) -> object: ...


def _now() -> Instant:
    return Instant(datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ"))


def _workspace_payload(workspace: object) -> dict[str, object]:
    item = cast(Workspace, workspace)
    return {
        "id": str(item.id),
        "name": item.name,
        "description": item.description,
        "state": item.state,
    }


def _etag(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return '"' + hashlib.sha256(encoded.encode("utf-8")).hexdigest() + '"'


def _manifest_payload(manifest: ProjectManifest) -> dict[str, object]:
    return manifest.to_data()


def _finops_payload(item: object) -> dict[str, object]:
    """Serialize FinOps records without coercing missing values into estimates."""
    values = getattr(item, "__dict__", {})
    payload: dict[str, object] = {}
    for key, value in values.items():
        if key.startswith("_"):
            continue
        if hasattr(value, "value"):
            value = value.value
        elif hasattr(value, "isoformat"):
            value = value.isoformat()
        elif isinstance(value, (int, float)):
            value = str(value)
        elif isinstance(value, dict):
            value = dict(value)
        payload[key] = value
    return payload


_PageItem = TypeVar("_PageItem")


def _page(
    items: Sequence[_PageItem], *, limit: int, offset: int
) -> tuple[list[_PageItem], str | None]:
    selected = list(items[offset : offset + limit])
    next_offset = offset + len(selected)
    cursor = None if next_offset >= len(items) else _encode_cursor(next_offset)
    return selected, cursor


def _encode_cursor(offset: int) -> str:
    raw = str(offset).encode("ascii")
    return "cp1." + base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(value: str | None) -> int:
    if value is None:
        return 0
    if (
        not value
        or value != value.strip()
        or len(value.encode("utf-8")) > _MAX_CURSOR_BYTES
        or not value.startswith("cp1.")
    ):
        raise ValueError("cursor is invalid")
    encoded = value[4:]
    padding = "=" * (-len(encoded) % 4)
    try:
        raw = base64.urlsafe_b64decode((encoded + padding).encode("ascii"))
        text = raw.decode("ascii")
        offset = int(text)
    except (UnicodeEncodeError, UnicodeDecodeError, ValueError) as exc:
        raise ValueError("cursor is invalid") from exc
    if offset < 0 or str(offset) != text:
        raise ValueError("cursor is invalid")
    return offset


def _list_query(query: str) -> tuple[int, int]:
    if not query:
        return _DEFAULT_LIST_LIMIT, 0
    values: dict[str, str] = {}
    for pair in query.split("&"):
        if not pair or "=" not in pair:
            raise ValueError("query parameters must use key=value form")
        key, value = pair.split("=", 1)
        key = unquote(key)
        value = unquote(value)
        if key not in {"limit", "cursor"}:
            raise ValueError(f"unknown query parameter: {key}")
        if key in values:
            raise ValueError(f"query parameter {key} must appear at most once")
        values[key] = value
    limit = _DEFAULT_LIST_LIMIT
    if "limit" in values:
        try:
            limit = int(values["limit"])
        except ValueError as exc:
            raise ValueError("limit must be an integer") from exc
        if not 1 <= limit <= _MAX_LIST_LIMIT:
            raise ValueError(f"limit must be between 1 and {_MAX_LIST_LIMIT}")
    return limit, _decode_cursor(values.get("cursor"))


def _segments(path: str) -> tuple[str, ...]:
    raw = path.split("/")
    if any(segment == "" for segment in raw[1:-1]):
        raise ValueError("path contains an empty segment")
    return tuple(unquote(segment) for segment in raw if segment)


class FeatureDefinitionServicePort(Protocol):
    def list(self, workspace_id: WorkspaceId) -> tuple[Any, ...]: ...

    def get(self, workspace_id: WorkspaceId, feature_id: str, version: int) -> Any: ...

    def publish_payload(self, workspace_id: WorkspaceId, payload: object) -> Any: ...


class ConnectorCapabilityPort(Protocol):
    def capability_payload(self) -> dict[str, object]: ...


class WorkspaceProjectHTTPServer(ThreadingHTTPServer):
    """HTTP adapter with injected authentication/authorization policy boundaries."""

    daemon_threads = True

    def __init__(
        self,
        server_address: tuple[str, int],
        workspace_service: WorkspaceService,
        project_service: ProjectService,
        *,
        authenticator: ControlPlaneAuthenticator,
        authorizer: ControlPlaneAuthorizer,
        workflow_reader: WorkflowReader | None = None,
        workflow_canceller: WorkflowCanceller | None = None,
        workflow_runner: WorkflowRunner | None = None,
        graph_query_reader: GraphQueryReader | None = None,
        graph_action_reader: GraphActionReader | None = None,
        ontology_reader: OntologyReader | None = None,
        catalog_reader: CatalogReader | None = None,
        data_engineering_reader: DataEngineeringRevisionReader | None = None,
        notebook_reader: NotebookReader | None = None,
        glossary_reader: GlossaryReader | None = None,
        streaming_health_reader: StreamingHealthReader | None = None,
        semantic_reader: SemanticReader | None = None,
        sql_reader: SqlReader | None = None,
        quality_reader: QualityHTTPAdapter | None = None,
        alert_reader: AlertReader | None = None,
        feature_definition_service: FeatureDefinitionServicePort | None = None,
        finops_reader: FinOpsReader | None = None,
        environment_service: EnvironmentService | None = None,
        binding_service: DeploymentBindingService | None = None,
        plugin_host: PluginDiagnostics | None = None,
        connector_registry: ConnectorCapabilityPort | None = None,
        ingestion_adapter: object | None = None,
        plugin_routes_enabled: bool = False,
        studio_root: Path | None = None,
        request_timeout_seconds: float = 15.0,
        audit_mutation: ControlPlaneAuditHook | None = None,
    ) -> None:
        if request_timeout_seconds <= 0:
            raise ValueError("request_timeout_seconds must be positive")
        self.workspace_service = workspace_service
        self.project_service = project_service
        self.authenticator = authenticator
        self.authorizer = authorizer
        self.workflow_reader = workflow_reader
        self.workflow_canceller = workflow_canceller
        self.workflow_runner = workflow_runner
        self.graph_query_reader = graph_query_reader
        self.graph_action_reader = graph_action_reader
        self.ontology_reader = ontology_reader
        self.catalog_reader = catalog_reader
        self.data_engineering_reader = data_engineering_reader
        self.notebook_reader = notebook_reader
        self.glossary_reader = glossary_reader
        self.streaming_health_reader = streaming_health_reader
        self.semantic_reader = semantic_reader
        self.sql_reader = sql_reader
        self.quality_reader = quality_reader
        self.alert_reader = alert_reader
        self.feature_definition_service = feature_definition_service
        self.finops_reader = finops_reader
        self.environment_service = environment_service
        self.binding_service = binding_service
        self.plugin_host = plugin_host
        self.connector_registry = connector_registry
        self.ingestion_adapter = ingestion_adapter
        self.plugin_routes_enabled = plugin_routes_enabled
        self.studio_root = studio_root.resolve() if studio_root is not None else None
        self.request_timeout_seconds = request_timeout_seconds
        self.audit_mutation = audit_mutation
        super().__init__(server_address, _WorkspaceProjectHandler)


class _WorkspaceProjectHandler(BaseHTTPRequestHandler):
    # Requests may be rejected before their body is parsed (auth/readiness).
    # Closing each response prevents unread bytes from becoming a second
    # request on the same socket, especially on Windows.
    protocol_version = "HTTP/1.0"

    def log_message(self, _format: str, *args: object) -> None:
        del args

    def _server(self) -> WorkspaceProjectHTTPServer:
        return cast(WorkspaceProjectHTTPServer, self.server)

    def _write_json(self, status: HTTPStatus, payload: object, *, etag: str | None = None) -> None:
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        if etag is not None:
            self.send_header("ETag", etag)
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status: HTTPStatus, code: str, message: str) -> None:
        self._write_json(status, {"error": {"code": code, "message": message}})

    def _discard_request_body(self) -> None:
        """Consume a bounded rejected body without decoding or validating it.

        Windows may reset a socket when a handler responds while unread request
        bytes remain buffered. Early auth/readiness failures must still avoid
        parsing the body, but they can safely drain its declared bytes.
        """
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            return
        try:
            length = int(raw_length)
        except ValueError:
            return
        if length <= 0 or length > _MAX_REQUEST_BYTES:
            return
        self.connection.settimeout(self._server().request_timeout_seconds)
        try:
            self.rfile.read(length)
        except (OSError, TimeoutError):
            return

    def _check_if_match(self, current: object) -> bool:
        expected = self.headers.get("If-Match")
        if expected is not None and expected != _etag(current):
            self._error(
                HTTPStatus.PRECONDITION_FAILED,
                "etag_mismatch",
                "resource changed since it was read",
            )
            return False
        return True

    def _authenticate(self) -> Actor | None:
        try:
            actor = self._server().authenticator.authenticate(self.headers.get("Authorization"))
        except ControlPlaneUnavailable:
            self._discard_request_body()
            self._error(
                HTTPStatus.SERVICE_UNAVAILABLE,
                "authentication_unavailable",
                "authentication service unavailable",
            )
            return None
        if actor is None:
            self._discard_request_body()
            self._error(HTTPStatus.UNAUTHORIZED, "unauthorized", "valid authorization required")
            return None
        return actor

    def _authorize(
        self,
        actor: Actor,
        workspace_id: WorkspaceId,
        permission: Permission,
        *,
        resource_ref: str | None = None,
        hide_denial: bool = False,
    ) -> bool | None:
        try:
            decision = self._server().authorizer.authorize(
                actor,
                PolicyRequirement(workspace_id, permission, resource_ref),
            )
        except ControlPlaneUnavailable:
            self._discard_request_body()
            self._error(
                HTTPStatus.SERVICE_UNAVAILABLE,
                "authorization_unavailable",
                "authorization service unavailable",
            )
            return None
        if decision.allowed:
            return True
        if hide_denial:
            return False
        self._discard_request_body()
        self._error(
            HTTPStatus.FORBIDDEN, "forbidden", "required workspace permission is not granted"
        )
        return False

    def _audit_mutation(
        self,
        actor: Actor,
        action: str,
        workspace_id: WorkspaceId,
        metadata: dict[str, object],
    ) -> bool:
        hook = self._server().audit_mutation
        if hook is None:
            return True
        try:
            hook(actor, action, workspace_id, metadata)
        except Exception:
            self._error(
                HTTPStatus.SERVICE_UNAVAILABLE,
                "mutation_audit_unavailable",
                "mutation audit persistence is unavailable",
            )
            return False
        return True

    def _read_json(self) -> object:
        if self.headers.get("Transfer-Encoding") is not None:
            raise ValueError("Transfer-Encoding request bodies are not supported")
        length_header = self.headers.get("Content-Length")
        if length_header is None:
            raise ValueError("Content-Length is required")
        try:
            length = int(length_header)
        except ValueError as exc:
            raise ValueError("Content-Length must be an integer") from exc
        if length < 0 or length > _MAX_REQUEST_BYTES:
            raise ValueError("request body exceeds configured byte limit")
        self.connection.settimeout(self._server().request_timeout_seconds)
        try:
            body = self.rfile.read(length)
        except TimeoutError as exc:
            raise TimeoutError("request body read timed out") from exc
        if len(body) != length:
            raise ValueError("request body ended before Content-Length bytes were received")
        try:
            return decode_canonical_json(body)
        except (UnicodeDecodeError, ValueError) as exc:
            raise ValueError("request body must be valid canonical UTF-8 JSON") from exc

    def _split(self) -> tuple[tuple[str, ...], str]:
        split = urlsplit(self.path)
        return _segments(split.path), split.query

    def _serve_studio(self) -> bool:
        split = urlsplit(self.path)
        if not split.path.startswith("/studio/"):
            return False
        root = self._server().studio_root
        if root is None:
            return False
        relative = split.path.removeprefix("/studio/") or "index.html"
        candidate = (root / relative).resolve()
        if root not in candidate.parents and candidate != root:
            self.send_error(HTTPStatus.NOT_FOUND)
            return True
        if not candidate.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return True
        body = candidate.read_bytes()
        self.send_response(HTTPStatus.OK)
        content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        return True

    def _handle_failure(self, exc: Exception) -> None:
        if isinstance(exc, (WorkspaceServiceNotFound, EnvironmentServiceNotFound)):
            self._error(HTTPStatus.NOT_FOUND, "not_found", "requested resource does not exist")
        elif isinstance(exc, (WorkspaceServiceConflict, EnvironmentServiceConflict)):
            self._error(HTTPStatus.CONFLICT, "conflict", str(exc))
        elif isinstance(exc, TimeoutError):
            self._error(
                HTTPStatus.REQUEST_TIMEOUT, "request_timeout", "request body read timed out"
            )
        elif isinstance(exc, (TypeError, ValueError)):
            self._error(HTTPStatus.BAD_REQUEST, "invalid_request", str(exc))
        else:
            raise exc

    def do_GET(self) -> None:  # noqa: N802
        if self._serve_studio():
            return
        actor = self._authenticate()
        if actor is None:
            return
        try:
            segments, query = self._split()
            if segments[:3] == ("v1", "ml-studio", "features"):
                service = self._server().feature_definition_service
                if service is None:
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "ml_features_unavailable",
                        "feature definition service is not configured",
                    )
                    return
                params = parse_qs(query or "", keep_blank_values=True)
                workspace_value = params.pop("workspace_id", [None])[0]
                if workspace_value is None or params:
                    raise ValueError("feature requests require only workspace_id")
                workspace_id = WorkspaceId(workspace_value)
                if not self._authorize(actor, workspace_id, "project.read"):
                    return
                if len(segments) == 3:
                    items = service.list(workspace_id)
                elif len(segments) == 5:
                    try:
                        version = int(unquote(segments[4]))
                    except ValueError as exc:
                        raise ValueError("feature version must be an integer") from exc
                    items = (service.get(workspace_id, unquote(segments[3]), version),)
                else:
                    self._method_or_not_found("GET", segments)
                    return
                self._write_json(HTTPStatus.OK, {"items": [item.to_payload() for item in items]})
                return
            if (
                len(segments) == 7
                and segments[:2] == ("v1", "workspaces")
                and segments[3] == "catalog"
                and segments[4] == "lineage"
            ):
                catalog_reader = self._server().catalog_reader
                if catalog_reader is None:
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "catalog_unavailable",
                        "catalog lineage reader is not configured",
                    )
                    return
                params = parse_qs(query or "", keep_blank_values=True)
                direction = params.get("direction", ["upstream"])[0]
                if direction not in {"upstream", "downstream"} or any(
                    key != "direction" for key in params
                ):
                    raise ValueError("lineage direction must be upstream or downstream")
                workspace_id = WorkspaceId(segments[2])
                if not self._authorize(actor, workspace_id, "workspace.read"):
                    return
                ref = AssetRef(AssetId(unquote(segments[5])), AssetVersion(unquote(segments[6])))
                method = getattr(catalog_reader, direction, None)
                if not callable(method):
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "catalog_unavailable",
                        "catalog lineage reader is not configured",
                    )
                    return
                edges = method(workspace_id, ref)
                self._write_json(HTTPStatus.OK, {"items": [edge.to_payload() for edge in edges]})
                return
            if segments == ("v1", "platform", "connectors"):
                if query:
                    raise ValueError("connector capabilities does not accept query parameters")
                registry = self._server().connector_registry
                if registry is None:
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "connectors_unavailable",
                        "connector registry is not configured",
                    )
                    return
                self._write_json(HTTPStatus.OK, registry.capability_payload())
                return
            if segments == ("v1", "platform", "plugins"):
                if query:
                    raise ValueError("plugin diagnostics does not accept query parameters")
                plugin_host = self._server().plugin_host
                if plugin_host is None:
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "plugins_unavailable",
                        "plugin host is not configured",
                    )
                    return
                diagnostics = list(plugin_host.diagnostics())
                contributions = plugin_host.contribution_diagnostics()
                ready = {item["id"] for item in diagnostics if item.get("state") == "ready"}
                surfaces = [
                    item
                    for item in cast(list[dict[str, object]], contributions["surfaces"])
                    if str(item.get("plugin_id")) in ready
                ]
                cli = [
                    item
                    for item in cast(list[dict[str, object]], contributions["cli"])
                    if any(surface.get("id") == item.get("id") for surface in surfaces)
                ]
                client_operations = [
                    item
                    for item in cast(list[dict[str, object]], contributions["client_operations"])
                    if any(surface.get("id") == item.get("id") for surface in surfaces)
                ]
                self._write_json(
                    HTTPStatus.OK,
                    {
                        "items": diagnostics,
                        "surfaces": surfaces,
                        "cli": cli,
                        "client_operations": client_operations,
                    },
                )
                return
            if segments in {
                ("v1", "platform", "capabilities"),
                ("v1", "platform", "ui-manifest"),
            }:
                if query:
                    raise ValueError("platform capabilities does not accept query parameters")
                plugin_host = self._server().plugin_host
                if not isinstance(plugin_host, PluginDiagnostics):
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "plugins_unavailable",
                        "plugin host is not configured",
                    )
                    return
                states = {item["id"]: item["state"] for item in plugin_host.diagnostics()}
                contributions = plugin_host.contribution_diagnostics()
                if segments[-1] == "capabilities":
                    payload = {
                        key: value
                        for key, value in cast(
                            dict[str, object], contributions["capabilities"]
                        ).items()
                        if states.get(str(value)) == "ready"
                    }
                else:
                    ui_items = cast(list[dict[str, object]], contributions["ui"])
                    payload = {
                        "items": [
                            item
                            for item in ui_items
                            if states.get(str(item.get("plugin_id"))) == "ready"
                        ]
                    }
                self._write_json(HTTPStatus.OK, payload)
                return
            if self._server().plugin_routes_enabled:
                plugin_host = self._server().plugin_host
                if isinstance(plugin_host, PluginRouter):
                    resolved = plugin_host.resolve_route("GET", urlsplit(self.path).path)
                    if resolved is not None:
                        route, parameters = resolved
                        permission = getattr(route, "permission", "")
                        workspace_value = parameters.get("workspace_id")
                        if workspace_value is None and (
                            permission.startswith("data-engineering:")
                            or permission.startswith("ml-studio:")
                        ):
                            workspace_value = parse_qs(query).get("workspace_id", [None])[0]
                        if workspace_value is not None:
                            workspace_id = WorkspaceId(workspace_value)
                            mapped_permission = {
                                "workspaces:read": "workspace.read",
                                "workspaces:write": "workspace.write",
                                "projects:read": "project.read",
                                "projects:write": "project.write",
                                "synthetic:read": "project.read",
                                "ml-studio:read": "project.read",
                                "ml-studio:write": "project.write",
                                "ml-studio:execute": "scheduler.write",
                                "data-engineering:read": "project.read",
                                "data-engineering:write": "project.write",
                                "data-engineering:execute": "scheduler.write",
                            }.get(permission)
                            if mapped_permission is None:
                                self._error(
                                    HTTPStatus.FORBIDDEN,
                                    "plugin_permission_unmapped",
                                    "plugin route permission is not mapped",
                                )
                                return
                            if not self._authorize(actor, workspace_id, mapped_permission):
                                return
                        elif permission == "synthetic:read":
                            workspace_value = parse_qs(query).get("workspace_id", [None])[0]
                            if workspace_value is None or not self._authorize(
                                actor, WorkspaceId(workspace_value), "project.read"
                            ):
                                return
                        payload = plugin_host.invoke_route(
                            "GET", urlsplit(self.path).path, query=query
                        )
                        self._write_json(HTTPStatus.OK, payload)
                        return
            if (
                len(segments) == 7
                and segments[:2] == ("v1", "workspaces")
                and segments[3] == "projects"
                and segments[5:] == ("semantic", "dashboards")
            ):
                semantic_reader = self._server().semantic_reader
                if semantic_reader is None:
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "semantic_unavailable",
                        "semantic service is not configured",
                    )
                    return
                workspace_id = WorkspaceId(segments[2])
                project_id = unquote(segments[4])
                if not self._authorize(
                    actor, workspace_id, "project.read", resource_ref=project_id
                ):
                    return
                self._write_json(HTTPStatus.OK, semantic_reader.list_dashboards(project_id))
                return
            if (
                len(segments) == 8
                and segments[:2] == ("v1", "workspaces")
                and segments[3] == "projects"
                and segments[5] == "notebooks"
            ):
                notebook_reader = self._server().notebook_reader
                if notebook_reader is None:
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "notebook_unavailable",
                        "Notebook service is not configured",
                    )
                    return
                workspace_id = WorkspaceId(segments[2])
                project_id = segments[4]
                if not self._authorize(
                    actor, workspace_id, "project.write", resource_ref=project_id
                ):
                    return
                if query:
                    raise ValueError("notebook replacement does not accept query parameters")
                body = self._read_json()
                if not isinstance(body, dict):
                    raise ValueError("notebook body must be an object")
                self._write_json(
                    HTTPStatus.OK,
                    notebook_reader.save(
                        project_id=project_id, notebook_id=segments[7], payload=body
                    ),
                )
                return
            if (
                len(segments) == 8
                and segments[:2] == ("v1", "workspaces")
                and segments[3] == "projects"
                and segments[5:7] == ("semantic", "dashboards")
            ):
                semantic_reader = self._server().semantic_reader
                if semantic_reader is None:
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "semantic_unavailable",
                        "semantic service is not configured",
                    )
                    return
                if query:
                    raise ValueError("dashboard read does not accept query parameters")
                workspace_id = WorkspaceId(segments[2])
                project_id = unquote(segments[4])
                dashboard_id = unquote(segments[7])
                if not self._authorize(
                    actor, workspace_id, "project.read", resource_ref=project_id
                ):
                    return
                dashboard_payload = semantic_reader.get_dashboard(project_id, dashboard_id)
                if dashboard_payload is None:
                    self._error(
                        HTTPStatus.NOT_FOUND, "not_found", "semantic dashboard does not exist"
                    )
                    return
                self._write_json(HTTPStatus.OK, dashboard_payload)
                return
            if (
                len(segments) == 8
                and segments[:2] == ("v1", "workspaces")
                and segments[3] == "projects"
                and segments[5] == "notebooks"
            ):
                notebook_reader = self._server().notebook_reader
                if notebook_reader is None:
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "notebook_unavailable",
                        "Notebook service is not configured",
                    )
                    return
                workspace_id = WorkspaceId(segments[2])
                project_id = segments[4]
                if not self._authorize(
                    actor, workspace_id, "project.write", resource_ref=project_id
                ):
                    return
                if query or self.headers.get("Content-Length") not in {None, "0"}:
                    raise ValueError("notebook delete does not accept query or body")
                revision = self.headers.get("If-Match")
                if revision is None or not revision.isdigit() or int(revision) < 1:
                    raise ValueError("If-Match must contain the expected positive revision")
                notebook_reader.delete(
                    project_id=project_id, notebook_id=segments[7], expected_revision=int(revision)
                )
                self._write_json(HTTPStatus.OK, {"deleted": True, "id": segments[7]})
                return
            if not self._registered_path(segments):
                self._method_or_not_found("GET", segments)
                return
            if segments == ("v1", "workspaces"):
                limit, offset = _list_query(query)
                visible: list[object] = []
                for workspace in self._server().workspace_service.list():
                    permitted = self._authorize(
                        actor, workspace.id, "workspace.read", hide_denial=True
                    )
                    if permitted is None:
                        return
                    if permitted:
                        visible.append(workspace)
                visible.sort(key=lambda item: str(cast(Workspace, item).id))
                selected, next_cursor = _page(visible, limit=limit, offset=offset)
                self._write_json(
                    HTTPStatus.OK,
                    {
                        "items": [_workspace_payload(item) for item in selected],
                        "next_cursor": next_cursor,
                    },
                )
                return
            if len(segments) == 3 and segments[:2] == ("v1", "workspaces"):
                if query:
                    raise ValueError("workspace read does not accept query parameters")
                workspace_id = WorkspaceId(segments[2])
                if not self._authorize(actor, workspace_id, "workspace.read"):
                    return
                workspace = self._server().workspace_service.get(workspace_id)
                payload = _workspace_payload(workspace)
                self._write_json(HTTPStatus.OK, payload, etag=_etag(payload))
                return
            if (
                len(segments) == 6
                and segments[:2] == ("v1", "workspaces")
                and segments[3] == "projects"
                and segments[5] == "bundle"
            ):
                if query:
                    raise ValueError("project bundle export does not accept query parameters")
                workspace_id = WorkspaceId(segments[2])
                project_ref = ProjectId(segments[4])
                if not self._authorize(
                    actor, workspace_id, "project.read", resource_ref=str(project_ref)
                ):
                    return
                manifest = self._server().project_service.get(workspace_id, project_ref)
                payload = _manifest_payload(manifest)
                self._write_json(HTTPStatus.OK, payload, etag=_etag(payload))
                return
            if (
                len(segments) == 7
                and segments[:2] == ("v1", "workspaces")
                and segments[3] == "projects"
                and segments[5:7] == ("bundle", "archive")
            ):
                if query:
                    raise ValueError(
                        "project Bundle archive export does not accept query parameters"
                    )
                workspace_id = WorkspaceId(segments[2])
                project_ref = ProjectId(segments[4])
                if not self._authorize(
                    actor, workspace_id, "project.read", resource_ref=str(project_ref)
                ):
                    return
                manifest = self._server().project_service.get(workspace_id, project_ref)
                archive_payload = manifest.to_json().encode("utf-8")
                if len(archive_payload) > 8 * 1024 * 1024:
                    raise ValueError("project manifest exceeds Bundle export limit")
                with tempfile.TemporaryDirectory(prefix="ronin-bundle-") as directory:
                    archive_path = Path(directory) / "project.roninbundle"
                    write_bundle(
                        archive_path,
                        (BundleFile(".ronin/project.json", "application/json", archive_payload),),
                    )
                    archive = archive_path.read_bytes()
                digest = hashlib.sha256(archive).hexdigest()
                self._write_json(
                    HTTPStatus.OK,
                    {
                        "media_type": "application/vnd.ronin.bundle+zip",
                        "digest": digest,
                        "size_bytes": len(archive),
                        "content_base64": base64.b64encode(archive).decode("ascii"),
                    },
                )
                return
            if (
                len(segments) in (7, 8)
                and segments[:2] == ("v1", "workspaces")
                and segments[3] == "projects"
                and segments[5] == "notebooks"
            ):
                notebook_reader = self._server().notebook_reader
                if notebook_reader is None:
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "notebook_unavailable",
                        "Notebook service is not configured",
                    )
                    return
                workspace_id = WorkspaceId(segments[2])
                project_id = segments[4]
                if not self._authorize(
                    actor, workspace_id, "project.read", resource_ref=project_id
                ):
                    return
                if query:
                    raise ValueError("notebook reads do not accept query parameters")
                if len(segments) == 7:
                    self._write_json(HTTPStatus.OK, notebook_reader.list(project_id=project_id))
                else:
                    self._write_json(
                        HTTPStatus.OK,
                        notebook_reader.get(project_id=project_id, notebook_id=segments[7]),
                    )
                return
            if (
                len(segments) == 6
                and segments[:2] == ("v1", "workspaces")
                and segments[3] == "projects"
                and segments[5] == "pipelines"
            ):
                de_reader = self._server().data_engineering_reader
                if de_reader is None:
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "data_engineering_unavailable",
                        "Data Engineering service is not configured",
                    )
                    return
                if query:
                    raise ValueError("pipeline listing does not accept query parameters")
                workspace_id = WorkspaceId(segments[2])
                project_id = segments[4]
                if not self._authorize(
                    actor, workspace_id, "project.read", resource_ref=project_id
                ):
                    return
                pipelines = de_reader.list_pipelines(project_id=project_id)
                self._write_json(
                    HTTPStatus.OK,
                    {"items": [{"pipeline_id": pipeline_id} for pipeline_id in pipelines]},
                )
                return
            if (
                len(segments) == 9
                and segments[:2] == ("v1", "workspaces")
                and segments[3] == "projects"
                and segments[5] == "pipelines"
                and segments[7:] == ("revisions", "compare")
            ):
                de_reader = self._server().data_engineering_reader
                if de_reader is None:
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "data_engineering_unavailable",
                        "Data Engineering service is not configured",
                    )
                    return
                workspace_id = WorkspaceId(segments[2])
                project_id, pipeline_id = segments[4], segments[6]
                if not self._authorize(
                    actor, workspace_id, "project.read", resource_ref=project_id
                ):
                    return
                params = parse_qs(query or "", keep_blank_values=True)
                try:
                    left_revision = int(params.get("left_revision", [""])[0])
                    right_revision = int(params.get("right_revision", [""])[0])
                except (KeyError, ValueError) as exc:
                    raise ValueError(
                        "compare requires integer left_revision and right_revision"
                    ) from exc
                self._write_json(
                    HTTPStatus.OK,
                    de_reader.compare(
                        project_id=project_id,
                        pipeline_id=pipeline_id,
                        left_revision=left_revision,
                        right_revision=right_revision,
                    ),
                )
                return
            if (
                len(segments) in {8, 9}
                and segments[:2] == ("v1", "workspaces")
                and segments[3] == "projects"
                and segments[5] == "pipelines"
                and segments[7] == "revisions"
            ):
                de_reader = self._server().data_engineering_reader
                if de_reader is None:
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "data_engineering_unavailable",
                        "Data Engineering service is not configured",
                    )
                    return
                if query:
                    raise ValueError("pipeline revision read does not accept query parameters")
                workspace_id = WorkspaceId(segments[2])
                project_id, pipeline_id = segments[4], segments[6]
                if not self._authorize(
                    actor, workspace_id, "project.read", resource_ref=project_id
                ):
                    return
                if len(segments) == 8:
                    revisions = de_reader.list_revisions(
                        project_id=project_id, pipeline_id=pipeline_id
                    )
                    self._write_json(HTTPStatus.OK, {"items": list(revisions)})
                else:
                    try:
                        revision_number = int(segments[8])
                    except ValueError as exc:
                        raise ValueError("pipeline revision must be an integer") from exc
                    item = de_reader.get_revision(
                        project_id=project_id, pipeline_id=pipeline_id, revision=revision_number
                    )
                    if item is None:
                        self._error(
                            HTTPStatus.NOT_FOUND, "not_found", "pipeline revision does not exist"
                        )
                        return
                    self._write_json(HTTPStatus.OK, item)
                return
            if (
                len(segments) == 7
                and segments[:2] == ("v1", "workspaces")
                and segments[3] == "schedules"
                and segments[5] == "history"
            ):
                workflow_reader = self._server().workflow_reader
                if workflow_reader is None:
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "scheduler_unavailable",
                        "workflow scheduler is not configured",
                    )
                    return
                params = parse_qs(query or "", keep_blank_values=True)
                if set(params) - {"limit"}:
                    raise ValueError("schedule history accepts only limit")
                try:
                    limit = int(params.get("limit", ["100"])[0])
                except ValueError as exc:
                    raise ValueError("schedule history limit must be an integer") from exc
                if limit < 1 or limit > 1000:
                    raise ValueError("schedule history limit must be between 1 and 1000")
                workspace_id = WorkspaceId(segments[2])
                if not self._authorize(actor, workspace_id, "scheduler.read"):
                    return
                fires = workflow_reader.list_schedule_fires(workspace_id, ScheduleId(segments[4]))
                self._write_json(
                    HTTPStatus.OK,
                    {
                        "items": [
                            {
                                "scheduled_for": str(fire.scheduled_for),
                                "workflow_run_id": str(fire.workflow_run_id),
                            }
                            for fire in fires[-limit:]
                        ]
                    },
                )
                return
            if (
                len(segments) == 7
                and segments[:2] == ("v1", "workspaces")
                and segments[3] == "schedules"
                and segments[5] == "next-runs"
            ):
                workflow_reader = self._server().workflow_reader
                if workflow_reader is None:
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "scheduler_unavailable",
                        "workflow scheduler is not configured",
                    )
                    return
                params = parse_qs(query or "", keep_blank_values=True)
                if set(params) - {"after", "count"} or "after" not in params:
                    raise ValueError("next-runs requires only after and optional count")
                after = params["after"][0]
                if not after:
                    raise ValueError("next-runs after must be non-empty")
                raw_count = params.get("count", ["10"])[0]
                try:
                    count = int(raw_count)
                except ValueError as exc:
                    raise ValueError("next-runs count must be an integer") from exc
                workspace_id = WorkspaceId(segments[2])
                if not self._authorize(actor, workspace_id, "scheduler.read"):
                    return
                values = workflow_reader.preview_schedule_next_runs(
                    workspace_id,
                    ScheduleId(segments[4]),
                    after=after,
                    count=count,
                )
                self._write_json(
                    HTTPStatus.OK,
                    {"items": [str(value) for value in values]},
                )
                return
            if (
                len(segments) == 4
                and segments[:2] == ("v1", "workspaces")
                and segments[3] == "event-deliveries"
            ):
                workflow_reader = self._server().workflow_reader
                if workflow_reader is None:
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "scheduler_unavailable",
                        "workflow scheduler is not configured",
                    )
                    return
                workspace_id = WorkspaceId(segments[2])
                if not self._authorize(actor, workspace_id, "scheduler.read"):
                    return
                limit, offset = _list_query(query)
                deliveries = workflow_reader.list_pending_deliveries(
                    workspace_id, limit=min(limit + offset, 1000)
                )
                delivery_items: list[EventDelivery] = list(deliveries)
                selected, next_cursor = _page(delivery_items, limit=limit, offset=offset)
                selected_deliveries = cast(list[EventDelivery], selected)
                self._write_json(
                    HTTPStatus.OK,
                    {
                        "items": [
                            {
                                "event_id": delivery.event_id.value,
                                "trigger_id": delivery.trigger.id.value,
                                "workflow_id": delivery.trigger.workflow_id.value,
                                "state": delivery.state,
                            }
                            for delivery in selected_deliveries
                        ],
                        "next_cursor": next_cursor,
                    },
                )
                return
            if (
                len(segments) == 6
                and segments[:2] == ("v1", "workspaces")
                and segments[3] == "projects"
                and segments[5] == "permissions"
            ):
                if query:
                    raise ValueError("project permission inspection does not accept query parameters")
                workspace_id = WorkspaceId(segments[2])
                project_ref = ProjectId(segments[4])
                if not self._authorize(
                    actor, workspace_id, "project.read", resource_ref=str(project_ref)
                ):
                    return
                decisions = {}
                for permission in ("project.read", "project.write", "scheduler.write"):
                    decision = self._server().authorizer.authorize(
                        actor, PolicyRequirement(workspace_id, permission, str(project_ref))
                    )
                    decisions[permission] = {
                        "allowed": decision.allowed,
                        "reason": decision.reason,
                        "matched_roles": [getattr(role, "value", str(role)) for role in decision.matched_roles],
                    }
                self._write_json(
                    HTTPStatus.OK,
                    {"workspace_id": str(workspace_id), "project_id": str(project_ref), "permissions": decisions},
                )
                return
            if (
                len(segments) == 5
                and segments[:2] == ("v1", "workspaces")
                and segments[3] == "ontologies"
            ):
                ontology_reader = self._server().ontology_reader
                if ontology_reader is None:
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "ontology_unavailable",
                        "ontology service is not configured",
                    )
                    return
                workspace_id = WorkspaceId(segments[2])
                if not self._authorize(actor, workspace_id, "workspace.read"):
                    return
                ontology_id = OntologyId(segments[4])
                versions = ontology_reader.list_schema_versions(workspace_id, ontology_id)
                self._write_json(HTTPStatus.OK, {"items": [item.to_payload() for item in versions]})
                return
            if (
                len(segments) == 5
                and segments[:2] == ("v1", "workspaces")
                and segments[3:] == ("catalog", "assets")
            ):
                catalog_reader = self._server().catalog_reader
                if catalog_reader is None:
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "catalog_unavailable",
                        "catalog service is not configured",
                    )
                    return
                workspace_id = WorkspaceId(segments[2])
                if not self._authorize(actor, workspace_id, "workspace.read"):
                    return
                params = parse_qs(query or "", keep_blank_values=True)
                search = params.get("q", [""])[0].strip()
                limit = int(params.get("limit", [str(_DEFAULT_LIST_LIMIT)])[0])
                if not 1 <= limit <= _MAX_LIST_LIMIT:
                    raise ValueError("catalog limit must be between 1 and 100")
                catalog_assets = (
                    catalog_reader.search_assets(workspace_id, search, limit=limit)
                    if search
                    else catalog_reader.list_assets(workspace_id)[:limit]
                )
                include_governance = (
                    params.get("include_governance", ["false"])[0].casefold() == "true"
                )
                catalog_items: list[dict[str, object]] = []
                for catalog_asset_entry in catalog_assets:
                    catalog_asset = cast(CatalogAsset, catalog_asset_entry)
                    catalog_asset_payload = cast(dict[str, object], catalog_asset.to_payload())
                    if include_governance:
                        sensitivity = getattr(catalog_reader, "get_sensitivity", None)
                        ownership = getattr(catalog_reader, "get_ownership", None)
                        if callable(sensitivity):
                            sensitivity_value = sensitivity(
                                workspace_id, AssetId(str(catalog_asset.id))
                            )
                            catalog_asset_payload["sensitivity"] = (
                                None
                                if sensitivity_value is None
                                else sensitivity_value.to_payload()
                            )
                        if callable(ownership):
                            ownership_value = ownership(
                                workspace_id, AssetId(str(catalog_asset.id))
                            )
                            catalog_asset_payload["ownership"] = (
                                None if ownership_value is None else ownership_value.to_payload()
                            )
                    catalog_items.append(catalog_asset_payload)
                self._write_json(HTTPStatus.OK, {"items": catalog_items})
                return
            if (
                len(segments) == 5
                and segments[:2] == ("v1", "workspaces")
                and segments[3:] == ("glossary", "terms")
            ):
                glossary_reader = self._server().glossary_reader
                if glossary_reader is None:
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "glossary_unavailable",
                        "glossary service is not configured",
                    )
                    return
                workspace_id = WorkspaceId(segments[2])
                if not self._authorize(actor, workspace_id, "workspace.read"):
                    return
                params = parse_qs(query or "", keep_blank_values=True)
                search = params.get("q", [""])[0].strip()
                limit = int(params.get("limit", [str(_DEFAULT_LIST_LIMIT)])[0])
                if not 1 <= limit <= _MAX_LIST_LIMIT:
                    raise ValueError("glossary limit must be between 1 and 100")
                glossary_terms = (
                    glossary_reader.search(workspace_id, search, limit=limit)
                    if search
                    else glossary_reader.list_latest(workspace_id)[:limit]
                )
                self._write_json(
                    HTTPStatus.OK,
                    {"items": [cast(GlossaryTerm, term).to_payload() for term in glossary_terms]},
                )
                return
            if (
                len(segments) == 6
                and segments[:2] == ("v1", "workspaces")
                and segments[3] == "streams"
                and segments[5] == "health"
            ):
                streaming_reader = self._server().streaming_health_reader
                if streaming_reader is None:
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "streaming_unavailable",
                        "streaming health is not configured",
                    )
                    return
                if query:
                    raise ValueError("stream health does not accept query parameters")
                workspace_id = WorkspaceId(segments[2])
                if not self._authorize(actor, workspace_id, "workspace.read"):
                    return
                self._write_json(HTTPStatus.OK, streaming_reader.health(workspace_id, segments[4]))
                return
            if (
                len(segments) == 7
                and segments[:2] == ("v1", "workspaces")
                and segments[3] == "projects"
                and segments[5:] == ("semantic", "models")
            ):
                semantic_reader = self._server().semantic_reader
                if semantic_reader is None:
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "semantic_unavailable",
                        "semantic service is not configured",
                    )
                    return
                if query:
                    raise ValueError("semantic model listing does not accept query parameters")
                workspace_id = WorkspaceId(segments[2])
                project_id = unquote(segments[4])
                if not self._authorize(
                    actor, workspace_id, "project.read", resource_ref=project_id
                ):
                    return
                self._write_json(HTTPStatus.OK, semantic_reader.list_models(project_id))
                return
            if (
                len(segments) == 6
                and segments[:2] == ("v1", "workspaces")
                and segments[3] == "ontologies"
            ):
                ontology_reader = self._server().ontology_reader
                if ontology_reader is None:
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "ontology_unavailable",
                        "ontology service is not configured",
                    )
                    return
                if query:
                    raise ValueError("ontology read does not accept query parameters")
                workspace_id = WorkspaceId(segments[2])
                if not self._authorize(actor, workspace_id, "workspace.read"):
                    return
                ontology = ontology_reader.get_schema(
                    workspace_id, OntologyId(segments[4]), segments[5]
                )
                if ontology is None:
                    self._error(HTTPStatus.NOT_FOUND, "not_found", "ontology schema does not exist")
                    return
                self._write_json(HTTPStatus.OK, ontology.to_payload())
                return
            if (
                len(segments) == 7
                and segments[:2] == ("v1", "workspaces")
                and segments[3:5] == ("glossary", "terms")
            ):
                glossary_reader = self._server().glossary_reader
                if glossary_reader is None:
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "glossary_unavailable",
                        "glossary service is not configured",
                    )
                    return
                if query:
                    raise ValueError("glossary term read does not accept query parameters")
                workspace_id = WorkspaceId(segments[2])
                if not self._authorize(actor, workspace_id, "workspace.read"):
                    return
                glossary_term = glossary_reader.get(
                    workspace_id, GlossaryTermId(unquote(segments[5])), unquote(segments[6])
                )
                if glossary_term is None:
                    self._error(HTTPStatus.NOT_FOUND, "not_found", "glossary term does not exist")
                    return
                self._write_json(HTTPStatus.OK, cast(GlossaryTerm, glossary_term).to_payload())
                return
            if (
                len(segments) == 4
                and segments[:2] == ("v1", "workspaces")
                and segments[3] == "workflows"
            ):
                if self._server().workflow_reader is None:
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "scheduler_unavailable",
                        "workflow scheduler is not configured",
                    )
                    return
                workspace_id = WorkspaceId(segments[2])
                if not self._authorize(actor, workspace_id, "scheduler.read"):
                    return
                limit, offset = _list_query(query)
                workflow_reader = self._server().workflow_reader
                if workflow_reader is None:
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "scheduler_unavailable",
                        "workflow scheduler is not configured",
                    )
                    return
                workflow_entries = sorted(
                    workflow_reader.list_workflows(workspace_id),
                    key=lambda item: str(item.id),
                )
                workflow_page, next_cursor = _page(
                    list(workflow_entries), limit=limit, offset=offset
                )
                self._write_json(
                    HTTPStatus.OK,
                    {
                        "items": [
                            cast(WorkflowDefinition, item).to_payload() for item in workflow_page
                        ],
                        "next_cursor": next_cursor,
                    },
                )
                return
            if (
                len(segments) == 4
                and segments[:2] == ("v1", "workspaces")
                and segments[3] == "schedules"
            ):
                workflow_reader = self._server().workflow_reader
                if workflow_reader is None:
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "scheduler_unavailable",
                        "workflow scheduler is not configured",
                    )
                    return
                workspace_id = WorkspaceId(segments[2])
                if not self._authorize(actor, workspace_id, "scheduler.read"):
                    return
                limit, offset = _list_query(query)
                schedule_entries = sorted(
                    workflow_reader.list_schedules(workspace_id), key=lambda item: item.id.value
                )
                schedule_page, next_cursor = _page(
                    list(schedule_entries), limit=limit, offset=offset
                )
                self._write_json(
                    HTTPStatus.OK,
                    {
                        "items": [cast(Schedule, item).to_payload() for item in schedule_page],
                        "next_cursor": next_cursor,
                    },
                )
                return
            if (
                len(segments) == 5
                and segments[:2] == ("v1", "workspaces")
                and segments[3] == "schedules"
            ):
                workflow_reader = self._server().workflow_reader
                if workflow_reader is None:
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "scheduler_unavailable",
                        "workflow scheduler is not configured",
                    )
                    return
                if query:
                    raise ValueError("schedule read does not accept query parameters")
                workspace_id = WorkspaceId(segments[2])
                if not self._authorize(actor, workspace_id, "scheduler.read"):
                    return
                schedule = workflow_reader.get_schedule(workspace_id, ScheduleId(segments[4]))
                if schedule is None:
                    self._error(HTTPStatus.NOT_FOUND, "not_found", "schedule does not exist")
                    return
                self._write_json(HTTPStatus.OK, schedule.to_payload())
                return
            if (
                len(segments) == 4
                and segments[:2] == ("v1", "workspaces")
                and segments[3] == "event-triggers"
            ):
                workflow_reader = self._server().workflow_reader
                if workflow_reader is None:
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "scheduler_unavailable",
                        "workflow scheduler is not configured",
                    )
                    return
                workspace_id = WorkspaceId(segments[2])
                if not self._authorize(actor, workspace_id, "scheduler.read"):
                    return
                limit, offset = _list_query(query)
                trigger_entries = sorted(
                    workflow_reader.list_event_triggers(workspace_id),
                    key=lambda item: item.id.value,
                )
                trigger_page, next_cursor = _page(list(trigger_entries), limit=limit, offset=offset)
                self._write_json(
                    HTTPStatus.OK,
                    {
                        "items": [
                            cast(EventTriggerDefinition, item).to_payload() for item in trigger_page
                        ],
                        "next_cursor": next_cursor,
                    },
                )
                return
            if (
                len(segments) == 5
                and segments[:2] == ("v1", "workspaces")
                and segments[3] == "backfills"
            ):
                workflow_reader = self._server().workflow_reader
                if workflow_reader is None:
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "scheduler_unavailable",
                        "workflow scheduler is not configured",
                    )
                    return
                if query:
                    raise ValueError("backfill read does not accept query parameters")
                workspace_id = WorkspaceId(segments[2])
                if not self._authorize(actor, workspace_id, "scheduler.read"):
                    return
                stored = workflow_reader.get_backfill(workspace_id, BackfillId(segments[4]))
                if stored is None:
                    self._error(HTTPStatus.NOT_FOUND, "not_found", "backfill does not exist")
                    return
                self._write_json(
                    HTTPStatus.OK,
                    {
                        "id": stored.id.value,
                        "schedule_id": stored.schedule_id.value,
                        "start_at": str(stored.start_at),
                        "end_at": str(stored.end_at),
                        "state": stored.state,
                    },
                )
                return
            if (
                len(segments) == 7
                and segments[:2] == ("v1", "workspaces")
                and segments[3] == "graphs"
                and segments[5] == "objects"
            ):
                graph_reader = self._server().graph_query_reader
                if graph_reader is None:
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "graph_unavailable",
                        "graph query is not configured",
                    )
                    return
                workspace_id = WorkspaceId(segments[2])
                if not self._authorize(actor, workspace_id, "workspace.read"):
                    return
                limit, _offset = _list_query(query)
                objects = graph_reader.list_objects(segments[4], segments[6], limit=limit)
                self._write_json(
                    HTTPStatus.OK,
                    {
                        "items": [
                            {
                                "object_type": item.ref.object_type,
                                "key": list(item.ref.key),
                                "properties": list(item.properties),
                            }
                            for item in objects
                        ],
                    },
                )
                return
            if (
                len(segments) == 5
                and segments[:2] == ("v1", "workspaces")
                and segments[3] == "workflow-runs"
            ):
                workflow_reader = self._server().workflow_reader
                if workflow_reader is None:
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "scheduler_unavailable",
                        "workflow scheduler is not configured",
                    )
                    return
                if query:
                    raise ValueError("workflow run read does not accept query parameters")
                workspace_id = WorkspaceId(segments[2])
                run_id = WorkflowRunId(segments[4])
                if not self._authorize(actor, workspace_id, "scheduler.read"):
                    return
                workflow_run = workflow_reader.get_run(workspace_id, run_id)
                if workflow_run is None:
                    self._error(HTTPStatus.NOT_FOUND, "not_found", "workflow run does not exist")
                    return
                tasks = workflow_reader.list_task_runs(workspace_id, run_id)
                payload = workflow_run.to_payload()
                payload["tasks"] = [
                    {
                        "id": task.id.value,
                        "workflow_run_id": task.workflow_run_id.value,
                        "node_id": task.node_id.value,
                        "state": task.state,
                        "attempt_count": task.attempt_count,
                    }
                    for task in tasks
                ]
                self._write_json(HTTPStatus.OK, payload)
                return
            if (
                len(segments) == 4
                and segments[:2] == ("v1", "workspaces")
                and segments[3] == "projects"
            ):
                workspace_id = WorkspaceId(segments[2])
                if not self._authorize(actor, workspace_id, "project.read"):
                    return
                limit, offset = _list_query(query)
                manifests = sorted(
                    self._server().project_service.list(workspace_id),
                    key=lambda item: str(item.project.id),
                )
                selected, next_cursor = _page(list(manifests), limit=limit, offset=offset)
                self._write_json(
                    HTTPStatus.OK,
                    {
                        "items": [
                            _manifest_payload(cast(ProjectManifest, item)) for item in selected
                        ],
                        "next_cursor": next_cursor,
                    },
                )
                return
            if (
                len(segments) == 6
                and segments[:2] == ("v1", "workspaces")
                and segments[3] == "projects"
                and segments[5] == "archive"
            ):
                if query:
                    raise ValueError("project archive does not accept query parameters")
                if self.headers.get("Content-Length") not in {None, "0"}:
                    raise ValueError("project archive does not accept a request body")
                workspace_id = WorkspaceId(segments[2])
                project_ref = ProjectId(segments[4])
                if not self._authorize(
                    actor, workspace_id, "project.write", resource_ref=str(project_ref)
                ):
                    return
                if not self._audit_mutation(
                    actor, "project.archive", workspace_id, {"resource": str(project_ref)}
                ):
                    return
                archived = self._server().project_service.archive(
                    workspace_id, project_ref, now=_now()
                )
                if not archived:
                    raise KeyError(f"{workspace_id}/{project_ref}")
                self._write_json(HTTPStatus.OK, {"archived": True, "project_id": str(project_ref)})
                return
            if (
                len(segments) == 7
                and segments[:2] == ("v1", "workspaces")
                and segments[3] == "projects"
                and segments[5:7] == ("bundle", "import")
            ):
                if query:
                    raise ValueError("project Bundle import does not accept query parameters")
                if not self.headers.get("Idempotency-Key", "").strip():
                    raise ValueError("Idempotency-Key header is required")
                workspace_id = WorkspaceId(segments[2])
                project_ref = ProjectId(segments[4])
                if not self._authorize(
                    actor, workspace_id, "project.write", resource_ref=str(project_ref)
                ):
                    return
                body = self._read_json()
                if not isinstance(body, dict) or not isinstance(body.get("content_base64"), str):
                    raise ValueError("Bundle import body must contain content_base64")
                try:
                    archive = base64.b64decode(body["content_base64"], validate=True)
                except (ValueError, TypeError) as exc:
                    raise ValueError("content_base64 must be valid Base64") from exc
                if len(archive) > 8 * 1024 * 1024:
                    raise ValueError("Bundle archive exceeds import limit")
                with tempfile.TemporaryDirectory(prefix="ronin-bundle-import-") as directory:
                    archive_path = Path(directory) / "import.roninbundle"
                    archive_path.write_bytes(archive)
                    verified = read_bundle_payload(archive_path, ".ronin/project.json")
                imported = ProjectManifest.from_json(verified.file.data.decode("utf-8"))
                if imported.project.id != project_ref:
                    raise ValueError("Bundle project id must match the request path")
                if not self._audit_mutation(
                    actor, "project.bundle.import", workspace_id, {"resource": str(project_ref)}
                ):
                    return
                existing = next(
                    (
                        item
                        for item in self._server().project_service.list(workspace_id)
                        if item.project.id == project_ref
                    ),
                    None,
                )
                if existing is not None:
                    if existing.to_json() != imported.to_json():
                        raise ValueError("project already exists with a different manifest")
                    imported_project = existing
                else:
                    imported_project = self._server().project_service.register(
                        workspace_id, imported, now=_now()
                    )
                self._write_json(
                    HTTPStatus.OK,
                    {
                        "project": _manifest_payload(imported_project),
                        "bundle_digest": hashlib.sha256(archive).hexdigest(),
                    },
                )
                return
            if (
                len(segments) == 8
                and segments[:2] == ("v1", "workspaces")
                and segments[3] == "projects"
                and segments[5] == "pipelines"
                and segments[7] == "revisions"
            ):
                de_writer = self._server().data_engineering_reader
                if de_writer is None:
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "data_engineering_unavailable",
                        "Data Engineering service is not configured",
                    )
                    return
                if query:
                    raise ValueError("pipeline revision import does not accept query parameters")
                workspace_id = WorkspaceId(segments[2])
                project_id, pipeline_id = segments[4], segments[6]
                if not self._authorize(
                    actor, workspace_id, "project.write", resource_ref=project_id
                ):
                    return
                body = self._read_json()
                if (
                    not isinstance(body, dict)
                    or not isinstance(body.get("project_name"), str)
                    or not isinstance(body.get("project_yaml_base64"), str)
                    or not isinstance(body.get("pipeline_documents"), list)
                ):
                    raise ValueError(
                        "revision body must contain project_name, project_yaml_base64, "
                        "and pipeline_documents"
                    )
                try:
                    project_yaml = base64.b64decode(body["project_yaml_base64"], validate=True)
                    documents = tuple(
                        (item["name"], base64.b64decode(item["content_base64"], validate=True))
                        for item in body["pipeline_documents"]
                        if isinstance(item, dict)
                        and isinstance(item.get("name"), str)
                        and isinstance(item.get("content_base64"), str)
                    )
                except (ValueError, TypeError, KeyError) as exc:
                    raise ValueError("revision document content must be valid Base64") from exc
                expected = body.get("expected_revision")
                if expected is not None and (
                    isinstance(expected, bool) or not isinstance(expected, int) or expected < 0
                ):
                    raise ValueError("expected_revision must be a non-negative integer")
                source = SdpProjectSource(body["project_name"], project_yaml, documents)
                if not self._audit_mutation(
                    actor,
                    "pipeline.revision.import",
                    workspace_id,
                    {"resource": f"{project_id}/{pipeline_id}"},
                ):
                    return
                record = de_writer.import_sdp(
                    project_id=project_id,
                    pipeline_id=pipeline_id,
                    source=source,
                    expected_revision=expected,
                )
                self._write_json(
                    HTTPStatus.CREATED,
                    {
                        "project_id": record.project_id,
                        "pipeline_id": record.pipeline_id,
                        "revision": record.revision,
                        "source_digest": record.source_digest,
                        "metadata_artifact": record.metadata_artifact.storage_ref,
                    },
                )
                return
            if (
                len(segments) == 8
                and segments[:2] == ("v1", "workspaces")
                and segments[3] == "projects"
                and segments[5] == "pipelines"
                and segments[7] == "archive"
            ):
                de_writer = self._server().data_engineering_reader
                if de_writer is None:
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "data_engineering_unavailable",
                        "Data Engineering service is not configured",
                    )
                    return
                if query:
                    raise ValueError("pipeline archive does not accept query parameters")
                if (
                    self.headers.get("Content-Length") not in {None, "0"}
                    or self.headers.get("Transfer-Encoding") is not None
                ):
                    raise ValueError("pipeline archive does not accept a request body")
                workspace_id = WorkspaceId(segments[2])
                project_id, pipeline_id = segments[4], segments[6]
                if not self._authorize(
                    actor, workspace_id, "project.write", resource_ref=project_id
                ):
                    return
                if not self._audit_mutation(
                    actor,
                    "pipeline.archive",
                    workspace_id,
                    {"resource": f"{project_id}/{pipeline_id}"},
                ):
                    return
                archived = de_writer.archive(project_id=project_id, pipeline_id=pipeline_id)
                self._write_json(
                    HTTPStatus.OK,
                    {"archived": archived, "project_id": project_id, "pipeline_id": pipeline_id},
                )
                return
            if (
                len(segments) == 4
                and segments[:2] == ("v1", "workspaces")
                and segments[3] == "environments"
            ):
                environment_service = self._server().environment_service
                if environment_service is None:
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "environments_unavailable",
                        "environment service is not configured",
                    )
                    return
                workspace_id = WorkspaceId(segments[2])
                if not self._authorize(actor, workspace_id, "workspace.read"):
                    return
                limit, offset = _list_query(query)
                environment_page, next_cursor = _page(
                    list(environment_service.list(workspace_id)), limit=limit, offset=offset
                )
                self._write_json(
                    HTTPStatus.OK,
                    {
                        "items": [item.to_payload() for item in environment_page],
                        "next_cursor": next_cursor,
                    },
                )
                return
            if (
                len(segments) == 5
                and segments[:2] == ("v1", "workspaces")
                and segments[3] == "environments"
            ):
                environment_service = self._server().environment_service
                if environment_service is None:
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "environments_unavailable",
                        "environment service is not configured",
                    )
                    return
                if query:
                    raise ValueError("environment read does not accept query parameters")
                workspace_id = WorkspaceId(segments[2])
                environment_id = EnvironmentId(segments[4])
                if not self._authorize(
                    actor, workspace_id, "workspace.read", resource_ref=str(environment_id)
                ):
                    return
                payload = environment_service.get(workspace_id, environment_id).to_payload()
                self._write_json(HTTPStatus.OK, payload, etag=_etag(payload))
                return
            if (
                len(segments) == 8
                and segments[3] == "projects"
                and segments[5] == "environments"
                and segments[7] == "bindings"
            ):
                binding_service = self._server().binding_service
                if binding_service is None:
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "environments_unavailable",
                        "binding service is not configured",
                    )
                    return
                if query:
                    raise ValueError("binding read does not accept query parameters")
                workspace_id = WorkspaceId(segments[2])
                binding_project_id = ProjectId(segments[4])
                environment_id = EnvironmentId(segments[6])
                if not self._authorize(
                    actor, workspace_id, "project.read", resource_ref=str(binding_project_id)
                ):
                    return
                self._write_json(
                    HTTPStatus.OK,
                    binding_service.get(
                        workspace_id, binding_project_id, environment_id
                    ).to_payload(),
                )
                return
            if (
                len(segments) == 5
                and segments[:2] == ("v1", "workspaces")
                and segments[3] == "projects"
            ):
                if query:
                    raise ValueError("project read does not accept query parameters")
                workspace_id = WorkspaceId(segments[2])
                project_ref = ProjectId(segments[4])
                if not self._authorize(
                    actor, workspace_id, "project.read", resource_ref=str(project_ref)
                ):
                    return
                manifest = self._server().project_service.get(workspace_id, project_ref)
                payload = _manifest_payload(manifest)
                self._write_json(HTTPStatus.OK, payload, etag=_etag(payload))
                return
            if (
                len(segments) == 7
                and segments[:2] == ("v1", "workspaces")
                and segments[3] == "quality"
                and segments[4] == "contracts"
            ):
                quality_reader = self._server().quality_reader
                if quality_reader is None:
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "quality_unavailable",
                        "quality service is not configured",
                    )
                    return
                if query:
                    raise ValueError("quality contract read does not accept query parameters")
                workspace_id = WorkspaceId(segments[2])
                if not self._authorize(
                    actor, workspace_id, "project.read", resource_ref=segments[5]
                ):
                    return
                payload = quality_reader.get_contract(
                    workspace_id, {"asset_id": segments[5], "version": segments[6]}
                ).to_payload()
                self._write_json(HTTPStatus.OK, payload, etag=_etag(payload))
                return
            if (
                len(segments) == 7
                and segments[:2] == ("v1", "workspaces")
                and segments[3] == "quality"
                and segments[4] == "runs"
            ):
                quality_reader = self._server().quality_reader
                if quality_reader is None:
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "quality_unavailable",
                        "quality service is not configured",
                    )
                    return
                if query:
                    raise ValueError("quality history does not accept query parameters")
                workspace_id = WorkspaceId(segments[2])
                if not self._authorize(
                    actor, workspace_id, "project.read", resource_ref=segments[5]
                ):
                    return
                payload = {"asset_id": segments[5], "version": segments[6]}
                self._write_json(
                    HTTPStatus.OK, {"items": list(quality_reader.history(workspace_id, payload))}
                )
                return
            if (
                len(segments) == 7
                and segments[:2] == ("v1", "workspaces")
                and segments[3] == "quality"
                and segments[4] == "state"
            ):
                quality_reader = self._server().quality_reader
                if quality_reader is None:
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "quality_unavailable",
                        "quality service is not configured",
                    )
                    return
                if query:
                    raise ValueError("quality state does not accept query parameters")
                workspace_id = WorkspaceId(segments[2])
                if not self._authorize(
                    actor, workspace_id, "project.read", resource_ref=segments[5]
                ):
                    return
                self._write_json(
                    HTTPStatus.OK,
                    quality_reader.state(
                        workspace_id, {"asset_id": segments[5], "version": segments[6]}
                    ),
                )
                return
            if (
                len(segments) == 5
                and segments[:2] == ("v1", "workspaces")
                and segments[3:] == ("alerts", "rules")
            ):
                alert_reader = self._server().alert_reader
                if alert_reader is None:
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "alerts_unavailable",
                        "alert service is not configured",
                    )
                    return
                if query:
                    raise ValueError("alert rule listing does not accept query parameters")
                workspace_id = WorkspaceId(segments[2])
                if not self._authorize(actor, workspace_id, "workspace.read"):
                    return
                self._write_json(HTTPStatus.OK, alert_reader.list_rules())
                return
            if (
                len(segments) == 5
                and segments[:2] == ("v1", "workspaces")
                and segments[3:] == ("alerts", "instances")
            ):
                alert_reader = self._server().alert_reader
                if alert_reader is None:
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "alerts_unavailable",
                        "alert service is not configured",
                    )
                    return
                workspace_id = WorkspaceId(segments[2])
                if not self._authorize(actor, workspace_id, "workspace.read"):
                    return
                alert_params = parse_qs(query or "", keep_blank_values=True)
                limit = int(alert_params.get("limit", ["100"])[0]) if query else 100
                self._write_json(HTTPStatus.OK, alert_reader.list_instances(limit=limit))
                return
            if (
                len(segments) == 5
                and segments[:2] == ("v1", "workspaces")
                and segments[3] == "finops"
                and segments[4] in {"usage", "costs", "budgets"}
            ):
                finops_reader = self._server().finops_reader
                if finops_reader is None:
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "finops_unavailable",
                        "finops service is not configured",
                    )
                    return
                workspace_id = WorkspaceId(segments[2])
                if not self._authorize(actor, workspace_id, "workspace.read"):
                    return
                params = parse_qs(query or "", keep_blank_values=True)
                kind = segments[4]
                if kind in {"usage", "costs"}:
                    period_start = params.get("period_start", [None])[0]
                    period_end = params.get("period_end", [None])[0]
                    if not period_start or not period_end:
                        raise ValueError(
                            "finops usage and costs require period_start and period_end"
                        )
                    finops_entries = getattr(finops_reader, f"list_{kind}")(
                        workspace_id, period_start=period_start, period_end=period_end
                    )
                else:
                    finops_entries = finops_reader.list_budgets(workspace_id)
                payload = {"items": [_finops_payload(item) for item in finops_entries]}
                self._write_json(HTTPStatus.OK, payload, etag=_etag(payload))
                return
            self._method_or_not_found("GET", segments)
        except Exception as exc:  # stable transport translation for domain/validation failures
            self._handle_failure(exc)

    def do_PATCH(self) -> None:  # noqa: N802
        actor = self._authenticate()
        if actor is None:
            return
        try:
            segments, query = self._split()
            if not self._registered_path(segments):
                self._method_or_not_found("PATCH", segments)
                return
            if len(segments) == 3 and segments[:2] == ("v1", "workspaces"):
                if query:
                    raise ValueError("workspace update does not accept query parameters")
                workspace_id = WorkspaceId(segments[2])
                if not self._authorize(actor, workspace_id, "workspace.admin"):
                    return
                current = self._server().workspace_service.get(workspace_id)
                if not self._check_if_match(_workspace_payload(current)):
                    return
                payload = self._read_json()
                if not isinstance(payload, dict) or set(payload) != {"name", "description"}:
                    raise ValueError(
                        "workspace update body must contain exactly name and description"
                    )
                name = payload["name"]
                description = payload["description"]
                if not isinstance(name, str):
                    raise TypeError("workspace name must be a string")
                if description is not None and not isinstance(description, str):
                    raise TypeError("workspace description must be a string or null")
                if not self._audit_mutation(
                    actor,
                    "workspace.update",
                    workspace_id,
                    {"resource": str(workspace_id)},
                ):
                    return
                workspace = self._server().workspace_service.update(
                    workspace_id,
                    name=name,
                    description=description,
                    now=_now(),
                )
                result = _workspace_payload(workspace)
                self._write_json(HTTPStatus.OK, result, etag=_etag(result))
                return
            self._method_or_not_found("PATCH", segments)
        except Exception as exc:
            self._handle_failure(exc)

    def do_POST(self) -> None:  # noqa: N802
        actor = self._authenticate()
        if actor is None:
            return
        try:
            segments, query = self._split()
            if segments == ("v1", "ml-studio", "features"):
                service = self._server().feature_definition_service
                if service is None:
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "ml_features_unavailable",
                        "feature definition service is not configured",
                    )
                    return
                params = parse_qs(query or "", keep_blank_values=True)
                workspace_value = params.pop("workspace_id", [None])[0]
                if workspace_value is None or params:
                    raise ValueError("feature requests require only workspace_id")
                workspace_id = WorkspaceId(workspace_value)
                if not self._authorize(actor, workspace_id, "project.write"):
                    return
                try:
                    stored = service.publish_payload(workspace_id, self._read_json())
                except RuntimeError as exc:
                    self._error(HTTPStatus.CONFLICT, "feature_conflict", str(exc))
                    return
                self._write_json(HTTPStatus.CREATED, stored.to_payload())
                return
            if segments == ("v1", "platform", "connectors", "preview"):
                if query:
                    raise ValueError("connector preview does not accept query parameters")
                adapter = self._server().ingestion_adapter
                preview = getattr(adapter, "preview", None) if adapter is not None else None
                if not callable(preview):
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "connectors_unavailable",
                        "ingestion preview is not configured",
                    )
                    return
                self._write_json(HTTPStatus.OK, preview(self._read_json()))
                return
            if segments in {
                ("v1", "platform", "connectors", "plan"),
                ("v1", "platform", "connectors", "checkpoint-health"),
            }:
                if query:
                    raise ValueError("connector operation does not accept query parameters")
                adapter = self._server().ingestion_adapter
                method_name = "plan" if segments[-1] == "plan" else "checkpoint_health"
                operation = getattr(adapter, method_name, None) if adapter is not None else None
                if not callable(operation):
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "connectors_unavailable",
                        f"connector {method_name} is not configured",
                    )
                    return
                self._write_json(HTTPStatus.OK, operation(self._read_json()))
                return
            if self._server().plugin_routes_enabled:
                plugin_host = self._server().plugin_host
                if isinstance(plugin_host, PluginRouter):
                    resolved = plugin_host.resolve_route("POST", urlsplit(self.path).path)
                    if resolved is not None:
                        route, parameters = resolved
                        workspace_value = parameters.get("workspace_id")
                        permission = getattr(route, "permission", "")
                        if workspace_value is None and (
                            permission.startswith("data-engineering:")
                            or permission.startswith("ml-studio:")
                        ):
                            workspace_value = parse_qs(query).get("workspace_id", [None])[0]
                        mapped_permission = {
                            "projects:write": "project.write",
                            "workspaces:write": "workspace.write",
                            "ai-studio:invoke": "workspace.read",
                            "synthetic:read": "project.read",
                            "ml-studio:read": "project.read",
                            "ml-studio:write": "project.write",
                            "ml-studio:execute": "scheduler.write",
                            "data-engineering:read": "project.read",
                            "data-engineering:write": "project.write",
                            "data-engineering:execute": "scheduler.write",
                            "synthetic:write": "project.write",
                            "synthetic:execute": "project.write",
                        }.get(permission)
                        if workspace_value is None and permission.startswith("synthetic:"):
                            workspace_value = parse_qs(query).get("workspace_id", [None])[0]
                        if workspace_value is None or mapped_permission is None:
                            self._error(
                                HTTPStatus.FORBIDDEN,
                                "plugin_permission_unmapped",
                                "plugin route permission is not mapped",
                            )
                            return
                        workspace_id = WorkspaceId(workspace_value)
                        if not self._authorize(actor, workspace_id, mapped_permission):
                            return
                        body = self._read_json()
                        if not self._audit_mutation(
                            actor,
                            "plugin.post",
                            workspace_id,
                            {"resource": urlsplit(self.path).path},
                        ):
                            return
                        payload = plugin_host.invoke_route(
                            "POST",
                            urlsplit(self.path).path,
                            query=query,
                            body=body,
                            idempotency_key=self.headers.get("Idempotency-Key"),
                        )
                        self._write_json(HTTPStatus.OK, payload)
                        return
            if segments == ("v1", "workspaces"):
                if query:
                    raise ValueError("workspace creation does not accept query parameters")
                if not self.headers.get("Idempotency-Key", "").strip():
                    raise ValueError("Idempotency-Key header is required")
                payload = self._read_json()
                if not isinstance(payload, dict) or set(payload) != {"id", "name", "description"}:
                    raise ValueError("workspace body must contain exactly id, name and description")
                raw_id, name, description = payload["id"], payload["name"], payload["description"]
                if not isinstance(raw_id, str) or not isinstance(name, str):
                    raise ValueError("workspace id and name must be strings")
                if description is not None and not isinstance(description, str):
                    raise ValueError("workspace description must be a string or null")
                workspace_id = WorkspaceId(raw_id)
                if not self._authorize(actor, workspace_id, "workspace.write"):
                    return
                if not self._audit_mutation(
                    actor, "workspace.create", workspace_id, {"resource": str(workspace_id)}
                ):
                    return
                workspace = self._server().workspace_service.create(
                    Workspace(workspace_id, name, description), now=_now()
                )
                result = _workspace_payload(workspace)
                self._write_json(HTTPStatus.CREATED, result, etag=_etag(result))
                return
            if (
                len(segments) == 8
                and segments[:2] == ("v1", "workspaces")
                and segments[3] == "projects"
                and segments[5] == "pipelines"
                and segments[7] == "runs"
            ):
                runner = self._server().workflow_runner
                if runner is None:
                    self._discard_request_body()
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "scheduler_unavailable",
                        "workflow scheduler is not configured",
                    )
                    return
                if query:
                    raise ValueError("pipeline run creation does not accept query parameters")
                workspace_id = WorkspaceId(segments[2])
                project_id, pipeline_id = segments[4], segments[6]
                if not self._authorize(
                    actor, workspace_id, "project.write", resource_ref=project_id
                ):
                    return
                payload = self._read_json()
                if not isinstance(payload, dict):
                    raise ValueError("pipeline run body must be a JSON object")
                required = {"revision_key", "ir_digest", "runtime"}
                if set(payload) - required - {"parameters"} or not required.issubset(payload):
                    raise ValueError(
                        "pipeline run body must contain revision_key, ir_digest, runtime, "
                        "and optional parameters"
                    )
                revision_key, ir_digest, runtime = (
                    payload["revision_key"],
                    payload["ir_digest"],
                    payload["runtime"],
                )
                parameters = payload.get("parameters", {})
                if (
                    not isinstance(revision_key, str)
                    or not revision_key.strip()
                    or not isinstance(ir_digest, str)
                    or len(ir_digest) != 64
                    or ir_digest != ir_digest.lower()
                    or any(c not in "0123456789abcdef" for c in ir_digest)
                    or not isinstance(runtime, str)
                    or not runtime.strip()
                    or not isinstance(parameters, dict)
                ):
                    raise ValueError("pipeline run fields have invalid types or values")
                workflow_id = WorkflowId(f"pipeline:{project_id}:{pipeline_id}")
                pipeline_data = parameters.get("pipeline")
                if pipeline_data is not None:
                    if not isinstance(pipeline_data, dict):
                        raise ValueError("parameters.pipeline must be an object")
                    pipeline = Pipeline.from_data(pipeline_data)
                    runner.put_workflow(
                        workspace_id,
                        WorkflowDefinition(workflow_id, pipeline.config.name, pipeline),
                    )
                trigger = Trigger(
                    "api",
                    f"{pipeline_id}:{revision_key}:{ir_digest}",
                    json.dumps(
                        {
                            "kind": "pipeline",
                            "project_id": project_id,
                            "pipeline_id": pipeline_id,
                            "revision_key": revision_key,
                            "ir_digest": ir_digest,
                            "runtime": runtime,
                            "parameters": parameters,
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                )
                if not self._audit_mutation(
                    actor,
                    "pipeline.run.create",
                    workspace_id,
                    {"resource": f"{project_id}/{pipeline_id}", "revision_key": revision_key},
                ):
                    return
                run = runner.create_workflow_run(
                    workspace_id,
                    workflow_id,
                    trigger,
                    idempotency_key=f"pipeline:{project_id}:{pipeline_id}:{revision_key}:{ir_digest}",
                )
                self._write_json(HTTPStatus.CREATED, run.to_payload())
                return
            if (
                len(segments) in (7, 8)
                and segments[:2] == ("v1", "workspaces")
                and segments[3] == "projects"
                and segments[5] == "notebooks"
            ):
                notebook_reader = self._server().notebook_reader
                if notebook_reader is None:
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "notebook_unavailable",
                        "Notebook service is not configured",
                    )
                    return
                workspace_id = WorkspaceId(segments[2])
                project_id = segments[4]
                if not self._authorize(
                    actor, workspace_id, "project.write", resource_ref=project_id
                ):
                    return
                body = self._read_json()
                if not isinstance(body, dict):
                    raise ValueError("notebook body must be an object")
                if len(segments) == 7:
                    self._write_json(
                        HTTPStatus.CREATED,
                        notebook_reader.create(project_id=project_id, payload=body),
                    )
                elif segments[7:] == ("archive",):
                    expected = body.get("expected_revision")
                    if isinstance(expected, bool) or not isinstance(expected, int) or expected < 1:
                        raise ValueError("expected_revision must be a positive integer")
                    self._write_json(
                        HTTPStatus.OK,
                        notebook_reader.archive(
                            project_id=project_id,
                            notebook_id=segments[6],
                            expected_revision=expected,
                        ),
                    )
                else:
                    self._method_or_not_found("POST", segments)
                return
            if (
                len(segments) == 7
                and segments[:2] == ("v1", "workspaces")
                and segments[3] == "projects"
                and segments[5:] == ("semantic", "query")
            ):
                semantic_reader = self._server().semantic_reader
                if semantic_reader is None:
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "semantic_unavailable",
                        "semantic service is not configured",
                    )
                    return
                if query:
                    raise ValueError("semantic query does not accept query parameters")
                workspace_id = WorkspaceId(segments[2])
                project_id = unquote(segments[4])
                if not self._authorize(
                    actor, workspace_id, "project.read", resource_ref=project_id
                ):
                    return
                self._write_json(
                    HTTPStatus.OK, semantic_reader.query(project_id, self._read_json())
                )
                return
            if (
                len(segments) == 7
                and segments[:2] == ("v1", "workspaces")
                and segments[3] == "projects"
                and segments[5:] == ("sql", "query")
            ):
                sql_reader = self._server().sql_reader
                if sql_reader is None:
                    self._discard_request_body()
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "sql_unavailable",
                        "SQL service is not configured",
                    )
                    return
                if query:
                    raise ValueError("SQL query does not accept query parameters")
                workspace_id = WorkspaceId(segments[2])
                project_id = unquote(segments[4])
                if not self._authorize(
                    actor, workspace_id, "project.read", resource_ref=project_id
                ):
                    return
                self._write_json(HTTPStatus.OK, sql_reader.query(project_id, self._read_json()))
                return
            if (
                len(segments) == 7
                and segments[:2] == ("v1", "workspaces")
                and segments[3] == "projects"
                and segments[5:] == ("semantic", "join")
            ):
                semantic_reader = self._server().semantic_reader
                if semantic_reader is None:
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "semantic_unavailable",
                        "semantic service is not configured",
                    )
                    return
                if query:
                    raise ValueError("semantic join does not accept query parameters")
                workspace_id = WorkspaceId(segments[2])
                project_id = unquote(segments[4])
                if not self._authorize(
                    actor, workspace_id, "project.read", resource_ref=project_id
                ):
                    return
                self._write_json(
                    HTTPStatus.OK, semantic_reader.join_query(project_id, self._read_json())
                )
                return
            if (
                len(segments) == 9
                and segments[:2] == ("v1", "workspaces")
                and segments[3] == "projects"
                and segments[5:7] == ("semantic", "dashboards")
                and segments[8] == "execute"
            ):
                semantic_reader = self._server().semantic_reader
                if semantic_reader is None:
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "semantic_unavailable",
                        "semantic service is not configured",
                    )
                    return
                workspace_id = WorkspaceId(segments[2])
                project_id = unquote(segments[4])
                dashboard_id = unquote(segments[7])
                if not self._authorize(
                    actor, workspace_id, "project.read", resource_ref=project_id
                ):
                    return
                if self.headers.get("Content-Length") not in {
                    None,
                    "0",
                } and self._read_json() not in ({}, None):
                    raise ValueError("dashboard execute does not accept a request body")
                if not self._audit_mutation(
                    actor,
                    "semantic.dashboard.execute",
                    workspace_id,
                    {"resource": f"{project_id}/{dashboard_id}"},
                ):
                    return
                self._write_json(
                    HTTPStatus.OK, semantic_reader.execute_dashboard(project_id, dashboard_id)
                )
                return
            if (
                len(segments) == 5
                and segments[:2] == ("v1", "workspaces")
                and segments[3:] == ("glossary", "terms")
            ):
                glossary_reader = self._server().glossary_reader
                if glossary_reader is None:
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "glossary_unavailable",
                        "glossary service is not configured",
                    )
                    return
                if query:
                    raise ValueError("glossary term creation does not accept query parameters")
                workspace_id = WorkspaceId(segments[2])
                if not self._authorize(actor, workspace_id, "workspace.admin"):
                    return
                term = GlossaryTerm.from_payload(self._read_json())
                if not self._audit_mutation(
                    actor,
                    "glossary.term.put",
                    workspace_id,
                    {"resource": f"{term.id}/{term.version}"},
                ):
                    return
                glossary_created = glossary_reader.put(workspace_id, term, now=_now())
                self._write_json(
                    HTTPStatus.CREATED, cast(GlossaryTerm, glossary_created).to_payload()
                )
                return
            if (
                len(segments) == 7
                and segments[:2] == ("v1", "workspaces")
                and segments[3:5] == ("catalog", "assets")
                and segments[6] == "revisions"
            ):
                catalog_reader = self._server().catalog_reader
                if catalog_reader is None or not callable(
                    getattr(catalog_reader, "list_revisions", None)
                ):
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "catalog_unavailable",
                        "catalog revision reader is not configured",
                    )
                    return
                if query:
                    raise ValueError("catalog revision listing does not accept query parameters")
                workspace_id = WorkspaceId(segments[2])
                if not self._authorize(actor, workspace_id, "workspace.read"):
                    return
                revisions = catalog_reader.list_revisions(
                    workspace_id, AssetId(unquote(segments[5]))
                )
                self._write_json(
                    HTTPStatus.OK, {"items": [revision.to_payload() for revision in revisions]}
                )
                return
            if (
                len(segments) == 8
                and segments[:2] == ("v1", "workspaces")
                and segments[3:5] == ("catalog", "assets")
                and segments[6] == "revisions"
            ):
                catalog_reader = self._server().catalog_reader
                if catalog_reader is None or not callable(
                    getattr(catalog_reader, "get_revision", None)
                ):
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "catalog_unavailable",
                        "catalog revision reader is not configured",
                    )
                    return
                if query:
                    raise ValueError("catalog revision read does not accept query parameters")
                workspace_id = WorkspaceId(segments[2])
                if not self._authorize(actor, workspace_id, "workspace.read"):
                    return
                revision = catalog_reader.get_revision(
                    workspace_id,
                    AssetRef(AssetId(unquote(segments[5])), AssetVersion(unquote(segments[7]))),
                )
                if revision is None:
                    self._error(
                        HTTPStatus.NOT_FOUND, "not_found", "catalog revision does not exist"
                    )
                    return
                self._write_json(HTTPStatus.OK, revision.to_payload())
                return
            if (
                len(segments) == 5
                and segments[:2] == ("v1", "workspaces")
                and segments[3:] == ("catalog", "assets")
            ):
                catalog_reader = self._server().catalog_reader
                if catalog_reader is None or not callable(
                    getattr(catalog_reader, "create_asset", None)
                ):
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "catalog_unavailable",
                        "catalog writer is not configured",
                    )
                    return
                if query:
                    raise ValueError("catalog asset creation does not accept query parameters")
                workspace_id = WorkspaceId(segments[2])
                if not self._authorize(actor, workspace_id, "workspace.admin"):
                    return
                asset = CatalogAsset.from_payload(self._read_json())
                if not self._audit_mutation(
                    actor, "catalog.asset.create", workspace_id, {"resource": str(asset.id)}
                ):
                    return
                stored = catalog_reader.create_asset(workspace_id, asset, now=_now())
                self._write_json(HTTPStatus.CREATED, stored.to_payload())
                return
            if (
                len(segments) == 7
                and segments[:2] == ("v1", "workspaces")
                and segments[3:5] == ("catalog", "assets")
                and segments[6] in {"sensitivity", "ownership"}
            ):
                catalog_reader = self._server().catalog_reader
                if catalog_reader is None:
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "catalog_unavailable",
                        "catalog service is not configured",
                    )
                    return
                if query:
                    raise ValueError("catalog governance mutation does not accept query parameters")
                workspace_id = WorkspaceId(segments[2])
                if not self._authorize(actor, workspace_id, "workspace.admin"):
                    return
                asset_id = AssetId(unquote(segments[5]))
                payload = self._read_json()
                if segments[6] == "sensitivity":
                    governance_metadata: SensitivityMetadata | OwnershipMetadata = (
                        SensitivityMetadata.from_payload(payload)
                    )
                    action = "catalog.sensitivity.put"
                    method = getattr(catalog_reader, "put_sensitivity", None)
                else:
                    governance_metadata = OwnershipMetadata.from_payload(payload)
                    action = "catalog.ownership.put"
                    method = getattr(catalog_reader, "put_ownership", None)
                if not callable(method):
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "catalog_governance_unavailable",
                        "catalog governance writer is not configured",
                    )
                    return
                if not self._audit_mutation(
                    actor,
                    action,
                    workspace_id,
                    {"resource": f"{asset_id}/{governance_metadata.version}"},
                ):
                    return
                stored = method(workspace_id, asset_id, governance_metadata, now=_now())
                self._write_json(HTTPStatus.CREATED, stored.to_payload())
                return
            if not self._registered_path(segments):
                self._method_or_not_found("POST", segments)
                return
            if (
                len(segments) == 6
                and segments[:2] == ("v1", "workspaces")
                and segments[3] == "workflows"
                and segments[5] == "runs"
            ):
                runner = self._server().workflow_runner
                if runner is None:
                    self._discard_request_body()
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "scheduler_unavailable",
                        "workflow scheduler is not configured",
                    )
                    return
                if query:
                    raise ValueError("workflow run creation does not accept query parameters")
                workspace_id = WorkspaceId(segments[2])
                workflow_id = WorkflowId(segments[4])
                if not self._authorize(
                    actor, workspace_id, "scheduler.write", resource_ref=str(workflow_id)
                ):
                    return
                payload = self._read_json()
                if not isinstance(payload, dict) or set(payload) != {"trigger", "idempotency_key"}:
                    raise ValueError("workflow run body must contain trigger and idempotency_key")
                idempotency_key = payload["idempotency_key"]
                if not isinstance(idempotency_key, str) or not idempotency_key.strip():
                    raise ValueError("idempotency_key must be a non-empty string")
                if not self._audit_mutation(
                    actor,
                    "workflow.run.create",
                    workspace_id,
                    {"resource": str(workflow_id)},
                ):
                    return
                run = runner.create_workflow_run(
                    workspace_id,
                    workflow_id,
                    Trigger.from_payload(payload["trigger"]),
                    idempotency_key=idempotency_key,
                )
                self._write_json(HTTPStatus.CREATED, run.to_payload())
                return
            if (
                len(segments) == 4
                and segments[:2] == ("v1", "workspaces")
                and segments[3] == "events"
            ):
                workflow_reader = self._server().workflow_reader
                if workflow_reader is None:
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "scheduler_unavailable",
                        "workflow scheduler is not configured",
                    )
                    return
                if query:
                    raise ValueError("event ingestion does not accept query parameters")
                workspace_id = WorkspaceId(segments[2])
                if not self._authorize(actor, workspace_id, "scheduler.write"):
                    return
                payload = self._read_json()
                if not isinstance(payload, dict):
                    raise ValueError("event body must be a JSON object")
                required = {"event_id", "event_type", "payload_digest", "occurred_at"}
                if set(payload) - required - {
                    "source_ref",
                    "subject_ref",
                    "received_at",
                } or not required.issubset(payload):
                    raise ValueError("event body has invalid fields")
                event = SchedulerEventRecord(
                    workspace_id,
                    SchedulerEventId(payload["event_id"]),
                    payload["event_type"],
                    payload.get("source_ref"),
                    payload.get("subject_ref"),
                    payload["payload_digest"],
                    Instant(payload["occurred_at"]),
                    Instant(payload.get("received_at", _now())),
                )
                if not self._audit_mutation(
                    actor,
                    "scheduler.event.ingest",
                    workspace_id,
                    {"resource": event.id.value},
                ):
                    return
                deliveries = workflow_reader.ingest_event(event)
                self._write_json(
                    HTTPStatus.ACCEPTED,
                    {
                        "event_id": event.id.value,
                        "deliveries": [delivery.state for delivery in deliveries],
                    },
                )
                return
            if (
                len(segments) in {4, 5}
                and segments[:2] == ("v1", "workspaces")
                and segments[3] == "backfills"
                and (len(segments) == 4 or segments[4] == "preview")
            ):
                workflow_reader = self._server().workflow_reader
                if workflow_reader is None:
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "scheduler_unavailable",
                        "workflow scheduler is not configured",
                    )
                    return
                workspace_id = WorkspaceId(segments[2])
                if not self._authorize(
                    actor,
                    workspace_id,
                    "scheduler.read" if segments[4:] == ("preview",) else "scheduler.write",
                ):
                    return
                payload = self._read_json()
                if segments[4:] == ("preview",):
                    if (
                        not isinstance(payload, dict)
                        or set(payload) - {"schedule_id", "start_at", "end_at", "max_runs"}
                        or not {"schedule_id", "start_at", "end_at"}.issubset(payload)
                    ):
                        raise ValueError("backfill preview body has invalid fields")
                    values = workflow_reader.preview_backfill(
                        workspace_id,
                        ScheduleId(payload["schedule_id"]),
                        start_at=Instant(payload["start_at"]),
                        end_at=Instant(payload["end_at"]),
                        max_runs=payload.get("max_runs", 1000),
                    )
                    self._write_json(HTTPStatus.OK, {"items": [str(value) for value in values]})
                    return
                if query:
                    raise ValueError("backfill creation does not accept query parameters")
                if not isinstance(payload, dict) or set(payload) != {
                    "id",
                    "schedule_id",
                    "start_at",
                    "end_at",
                }:
                    raise ValueError(
                        "backfill body must contain exactly id, schedule_id, start_at, end_at"
                    )
                request = BackfillRequest(
                    BackfillId(payload["id"]),
                    ScheduleId(payload["schedule_id"]),
                    Instant(payload["start_at"]),
                    Instant(payload["end_at"]),
                )
                if not self._audit_mutation(
                    actor,
                    "scheduler.backfill.create",
                    workspace_id,
                    {"resource": request.id.value},
                ):
                    return
                stored = workflow_reader.create_backfill(workspace_id, request)
                self._write_json(
                    HTTPStatus.CREATED,
                    {
                        "id": stored.id.value,
                        "schedule_id": stored.schedule_id.value,
                        "start_at": str(stored.start_at),
                        "end_at": str(stored.end_at),
                        "state": stored.state,
                    },
                )
                return
            if (
                len(segments) == 6
                and segments[:2] == ("v1", "workspaces")
                and segments[3] == "backfills"
                and segments[5] == "cancel"
            ):
                workflow_reader = self._server().workflow_reader
                if workflow_reader is None:
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "scheduler_unavailable",
                        "workflow scheduler is not configured",
                    )
                    return
                if query:
                    raise ValueError("backfill cancellation does not accept query parameters")
                workspace_id = WorkspaceId(segments[2])
                if not self._authorize(actor, workspace_id, "scheduler.write"):
                    return
                if not self._audit_mutation(
                    actor,
                    "scheduler.backfill.cancel",
                    workspace_id,
                    {"resource": segments[4]},
                ):
                    return
                stored = workflow_reader.cancel_backfill(workspace_id, BackfillId(segments[4]))
                self._write_json(HTTPStatus.OK, {"id": stored.id.value, "state": stored.state})
                return
            if (
                len(segments) == 6
                and segments[:2] == ("v1", "workspaces")
                and segments[3] == "graphs"
                and segments[5] == "actions"
            ):
                graph_action_reader = self._server().graph_action_reader
                if graph_action_reader is None:
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "graph_action_unavailable",
                        "graph actions are not configured",
                    )
                    return
                workspace_id = WorkspaceId(segments[2])
                if not self._authorize(actor, workspace_id, "workspace.write"):
                    return
                graph_action_payload = self._read_json()
                if not isinstance(graph_action_payload, dict):
                    raise ValueError("graph action body must be a JSON object")
                if not self._audit_mutation(
                    actor,
                    "graph.action.execute",
                    workspace_id,
                    {"resource": segments[4]},
                ):
                    return
                graph_action_result = graph_action_reader.execute_action_payload(
                    segments[4], graph_action_payload
                )
                self._write_json(HTTPStatus.OK, graph_action_result)
                return
            if (
                len(segments) == 6
                and segments[:2] == ("v1", "workspaces")
                and segments[3] == "graphs"
                and segments[5] == "neighbors"
            ):
                graph_query_reader = self._server().graph_query_reader
                if graph_query_reader is None:
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "graph_unavailable",
                        "graph query is not configured",
                    )
                    return
                workspace_id = WorkspaceId(segments[2])
                if not self._authorize(actor, workspace_id, "workspace.read"):
                    return
                payload = self._read_json()
                if (
                    not isinstance(payload, dict)
                    or set(payload) - {"object_type", "key", "limit"}
                    or not {"object_type", "key"}.issubset(payload)
                ):
                    raise ValueError("neighbor body must contain object_type and key")
                object_type, key = payload["object_type"], payload["key"]
                limit = payload.get("limit", 100)
                if (
                    not isinstance(object_type, str)
                    or not isinstance(key, list)
                    or not isinstance(limit, int)
                    or isinstance(limit, bool)
                ):
                    raise TypeError("neighbor fields have invalid types")
                ref = KnowledgeObjectRef(object_type, tuple(tuple(item) for item in key))
                neighbors = graph_query_reader.neighbors(segments[4], ref, limit=limit)
                self._write_json(
                    HTTPStatus.OK,
                    {
                        "items": [
                            {"object_type": item.object_type, "key": list(item.key)}
                            for item in neighbors
                        ]
                    },
                )
                return
            if (
                len(segments) == 6
                and segments[:2] == ("v1", "workspaces")
                and segments[3] == "graphs"
                and segments[5] == "query"
            ):
                graph_query_reader = self._server().graph_query_reader
                if graph_query_reader is None:
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "graph_unavailable",
                        "graph query is not configured",
                    )
                    return
                workspace_id = WorkspaceId(segments[2])
                if not self._authorize(actor, workspace_id, "workspace.read"):
                    return
                graph_payload = self._read_json()
                if (
                    not isinstance(graph_payload, dict)
                    or set(graph_payload) - {"query", "max_limit"}
                    or "query" not in graph_payload
                ):
                    raise ValueError("graph query body must contain query and optional max_limit")
                query = graph_payload["query"]
                max_limit = graph_payload.get("max_limit", 1000)
                if (
                    not isinstance(query, str)
                    or not isinstance(max_limit, int)
                    or isinstance(max_limit, bool)
                ):
                    raise TypeError("graph query fields have invalid types")
                graph_result = graph_query_reader.query(segments[4], query, max_limit=max_limit)
                objects = [
                    {
                        "object_type": item.ref.object_type,
                        "key": list(item.ref.key),
                        "properties": list(item.properties),
                    }
                    for item in graph_result.objects
                ]
                self._write_json(HTTPStatus.OK, {"objects": objects})
                return
            if (
                len(segments) == 6
                and segments[:2] == ("v1", "workspaces")
                and segments[3] == "workflow-runs"
                and segments[5] == "cancel"
            ):
                canceller = self._server().workflow_canceller
                if canceller is None:
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "scheduler_unavailable",
                        "workflow scheduler is not configured",
                    )
                    return
                if query or self.headers.get("Content-Length") not in {None, "0"}:
                    raise ValueError("workflow cancellation does not accept a query or body")
                workspace_id = WorkspaceId(segments[2])
                run_id = WorkflowRunId(segments[4])
                if not self._authorize(actor, workspace_id, "scheduler.write"):
                    return
                if not self._audit_mutation(
                    actor,
                    "workflow.run.cancel",
                    workspace_id,
                    {"resource": run_id.value},
                ):
                    return
                cancelled_jobs = canceller.cancel_workflow_run(workspace_id, run_id)
                self._write_json(
                    HTTPStatus.OK,
                    {"workflow_run_id": run_id.value, "cancelled_jobs": cancelled_jobs},
                )
                return
            if (
                len(segments) == 6
                and segments[:2] == ("v1", "workspaces")
                and segments[3] == "environments"
                and segments[5] == "diff"
            ):
                environment_service = self._server().environment_service
                if environment_service is None:
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "environments_unavailable",
                        "environment service is not configured",
                    )
                    return
                workspace_id = WorkspaceId(segments[2])
                environment_id = EnvironmentId(segments[4])
                if not self._authorize(
                    actor, workspace_id, "workspace.read", resource_ref=str(environment_id)
                ):
                    return
                proposed = EnvironmentDefinition.from_payload(self._read_json())
                if proposed.id != environment_id:
                    raise ValueError("environment id must match the request path")
                diff_result = diff_environments(
                    environment_service.get(workspace_id, environment_id), proposed
                )
                self._write_json(
                    HTTPStatus.OK,
                    {
                        "environment_id": str(diff_result.environment_id),
                        "changed": diff_result.changed,
                        "changed_fields": list(diff_result.changed_fields),
                    },
                )
                return
            if (
                len(segments) == 5
                and segments[:2] == ("v1", "workspaces")
                and segments[3:] == ("quality", "runs")
            ):
                quality_reader = self._server().quality_reader
                if quality_reader is None:
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "quality_unavailable",
                        "quality service is not configured",
                    )
                    return
                if query:
                    raise ValueError("quality run does not accept query parameters")
                workspace_id = WorkspaceId(segments[2])
                if not self._authorize(actor, workspace_id, "project.write"):
                    return
                body = self._read_json()
                if not isinstance(body, dict):
                    raise ValueError("quality run body must be an object")
                if not self._audit_mutation(
                    actor,
                    "quality.run.create",
                    workspace_id,
                    {"resource": str(body.get("asset_id", "quality-run"))},
                ):
                    return
                self._write_json(
                    HTTPStatus.CREATED, quality_reader.run(workspace_id, body, now=_now())
                )
                return
            if (
                len(segments) == 5
                and segments[:2] == ("v1", "workspaces")
                and segments[3:] == ("alerts", "evaluate")
            ):
                alert_reader = self._server().alert_reader
                if alert_reader is None:
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "alerts_unavailable",
                        "alert service is not configured",
                    )
                    return
                if query:
                    raise ValueError("alert evaluation does not accept query parameters")
                workspace_id = WorkspaceId(segments[2])
                if not self._authorize(actor, workspace_id, "workspace.write"):
                    return
                body = self._read_json()
                if not self._audit_mutation(
                    actor, "alert.evaluate", workspace_id, {"resource": "alert"}
                ):
                    return
                self._write_json(HTTPStatus.OK, alert_reader.evaluate(body, now=_now()))
                return
            if (
                len(segments) == 5
                and segments[:2] == ("v1", "workspaces")
                and segments[3:] == ("alerts", "acknowledge")
            ):
                alert_reader = self._server().alert_reader
                if alert_reader is None:
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "alerts_unavailable",
                        "alert service is not configured",
                    )
                    return
                if query:
                    raise ValueError("alert acknowledgement does not accept query parameters")
                workspace_id = WorkspaceId(segments[2])
                if not self._authorize(actor, workspace_id, "workspace.write"):
                    return
                body = self._read_json()
                if not self._audit_mutation(
                    actor, "alert.acknowledge", workspace_id, {"resource": "alert"}
                ):
                    return
                self._write_json(HTTPStatus.OK, alert_reader.acknowledge(body, now=_now()))
                return
            if (
                len(segments) == 4
                and segments[:2] == ("v1", "workspaces")
                and segments[3] == "archive"
            ):
                if query:
                    raise ValueError("workspace archive does not accept query parameters")
                workspace_id = WorkspaceId(segments[2])
                if not self._authorize(actor, workspace_id, "workspace.admin"):
                    return
                if (
                    self.headers.get("Content-Length") not in {None, "0"}
                    or self.headers.get("Transfer-Encoding") is not None
                ):
                    raise ValueError("workspace archive does not accept a request body")
                if not self._audit_mutation(
                    actor,
                    "workspace.archive",
                    workspace_id,
                    {"resource": str(workspace_id)},
                ):
                    return
                workspace = self._server().workspace_service.archive(workspace_id, now=_now())
                self._write_json(HTTPStatus.OK, _workspace_payload(workspace))
                return
            if (
                len(segments) == 4
                and segments[:2] == ("v1", "workspaces")
                and segments[3] == "projects"
            ):
                if query:
                    raise ValueError("project registration does not accept query parameters")
                workspace_id = WorkspaceId(segments[2])
                if not self._authorize(actor, workspace_id, "project.write"):
                    return
                payload = self._read_json()
                if not isinstance(payload, dict):
                    raise ValueError("project manifest body must be a JSON object")
                manifest = ProjectManifest.from_data(payload)
                if not self._audit_mutation(
                    actor,
                    "project.register",
                    workspace_id,
                    {"resource": str(manifest.project.id)},
                ):
                    return
                stored = self._server().project_service.register(workspace_id, manifest, now=_now())
                self._write_json(HTTPStatus.CREATED, _manifest_payload(stored))
                return
            if (
                len(segments) == 4
                and segments[:2] == ("v1", "workspaces")
                and segments[3] == "environments"
            ):
                environment_service = self._server().environment_service
                if environment_service is None:
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "environments_unavailable",
                        "environment service is not configured",
                    )
                    return
                workspace_id = WorkspaceId(segments[2])
                if not self._authorize(actor, workspace_id, "workspace.write"):
                    return
                environment = EnvironmentDefinition.from_payload(self._read_json())
                if not self._audit_mutation(
                    actor,
                    "environment.create",
                    workspace_id,
                    {"resource": str(environment.id)},
                ):
                    return
                stored = environment_service.create(workspace_id, environment, now=_now())
                self._write_json(HTTPStatus.CREATED, stored.to_payload())
                return
            if (
                len(segments) == 6
                and segments[3] == "environments"
                and segments[5] in {"disable", "enable"}
            ):
                environment_service = self._server().environment_service
                if environment_service is None:
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "environments_unavailable",
                        "environment service is not configured",
                    )
                    return
                workspace_id = WorkspaceId(segments[2])
                environment_id = EnvironmentId(segments[4])
                if not self._authorize(
                    actor, workspace_id, "workspace.write", resource_ref=str(environment_id)
                ):
                    return
                action = segments[5]
                if self._read_json() not in ({}, None):
                    raise ValueError(f"environment {action} body must be empty")
                if not self._audit_mutation(
                    actor,
                    f"environment.{action}",
                    workspace_id,
                    {"resource": str(environment_id)},
                ):
                    return
                self._write_json(
                    HTTPStatus.OK,
                    (
                        environment_service.disable(workspace_id, environment_id, now=_now())
                        if action == "disable"
                        else environment_service.enable(workspace_id, environment_id, now=_now())
                    ).to_payload(),
                )
                return
            self._method_or_not_found("POST", segments)
        except Exception as exc:
            self._handle_failure(exc)

    def do_PUT(self) -> None:  # noqa: N802
        actor = self._authenticate()
        if actor is None:
            return
        try:
            segments, query = self._split()
            if self._server().plugin_routes_enabled:
                plugin_host = self._server().plugin_host
                if isinstance(plugin_host, PluginRouter):
                    resolved = plugin_host.resolve_route("PUT", urlsplit(self.path).path)
                    if resolved is not None:
                        route, parameters = resolved
                        workspace_value = parameters.get("workspace_id")
                        mapped_permission = {
                            "projects:write": "project.write",
                            "workspaces:write": "workspace.write",
                            "ai-studio:write": "workspace.write",
                            "ai-studio:read": "workspace.read",
                        }.get(getattr(route, "permission", ""))
                        if workspace_value is None or mapped_permission is None:
                            self._error(
                                HTTPStatus.FORBIDDEN,
                                "plugin_permission_unmapped",
                                "plugin route permission is not mapped",
                            )
                            return
                        workspace_id = WorkspaceId(workspace_value)
                        project_id = parameters.get("project_id")
                        if not self._authorize(
                            actor,
                            workspace_id,
                            mapped_permission,
                            resource_ref=project_id,
                        ):
                            return
                        if not self._audit_mutation(
                            actor,
                            "plugin.put",
                            workspace_id,
                            {"resource": urlsplit(self.path).path},
                        ):
                            return
                        payload = plugin_host.invoke_route(
                            "PUT",
                            urlsplit(self.path).path,
                            query=query,
                            body=self._read_json(),
                        )
                        self._write_json(HTTPStatus.OK, payload)
                        return
            if (
                len(segments) == 8
                and segments[:2] == ("v1", "workspaces")
                and segments[3] == "projects"
                and segments[5:7] == ("semantic", "dashboards")
            ):
                semantic_reader = self._server().semantic_reader
                if semantic_reader is None:
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "semantic_unavailable",
                        "semantic service is not configured",
                    )
                    return
                if query:
                    raise ValueError("dashboard replacement does not accept query parameters")
                workspace_id = WorkspaceId(segments[2])
                project_id = unquote(segments[4])
                dashboard_id = unquote(segments[7])
                if not self._authorize(
                    actor, workspace_id, "project.write", resource_ref=project_id
                ):
                    return
                body = self._read_json()
                if not isinstance(body, dict) or body.get("id") != dashboard_id:
                    raise ValueError("dashboard body id must match dashboard_id path parameter")
                if not self._audit_mutation(
                    actor,
                    "semantic.dashboard.replace",
                    workspace_id,
                    {"resource": f"{project_id}/{dashboard_id}"},
                ):
                    return
                self._write_json(HTTPStatus.OK, semantic_reader.put_dashboard(project_id, body))
                return
            if not self._registered_path(segments):
                self._method_or_not_found("PUT", segments)
                return
            if (
                len(segments) == 5
                and segments[:2] == ("v1", "workspaces")
                and segments[3] == "projects"
            ):
                if query:
                    raise ValueError("project replacement does not accept query parameters")
                workspace_id = WorkspaceId(segments[2])
                project_ref = ProjectId(segments[4])
                if not self._authorize(
                    actor, workspace_id, "project.write", resource_ref=str(project_ref)
                ):
                    return
                try:
                    current = self._server().project_service.get(workspace_id, project_ref)
                except (WorkspaceServiceNotFound, WorkspaceServiceConflict):
                    self._discard_request_body()
                    raise
                if not self._check_if_match(_manifest_payload(current)):
                    return
                payload = self._read_json()
                if not isinstance(payload, dict):
                    raise ValueError("project manifest body must be a JSON object")
                manifest = ProjectManifest.from_data(payload)
                if manifest.project.id != project_ref:
                    raise ValueError("project manifest id must match the request path")
                if not self._audit_mutation(
                    actor,
                    "project.replace",
                    workspace_id,
                    {"resource": str(project_ref)},
                ):
                    return
                stored = self._server().project_service.replace(workspace_id, manifest, now=_now())
                project_result = _manifest_payload(stored)
                self._write_json(HTTPStatus.OK, project_result, etag=_etag(project_result))
                return
            if (
                len(segments) == 5
                and segments[:2] == ("v1", "workspaces")
                and segments[3] == "schedules"
            ):
                workflow_reader = self._server().workflow_reader
                if workflow_reader is None:
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "scheduler_unavailable",
                        "workflow scheduler is not configured",
                    )
                    return
                if query:
                    raise ValueError("schedule replacement does not accept query parameters")
                workspace_id = WorkspaceId(segments[2])
                schedule_id = ScheduleId(segments[4])
                if not self._authorize(
                    actor,
                    workspace_id,
                    "scheduler.write",
                    resource_ref=schedule_id.value,
                ):
                    return
                payload = self._read_json()
                if not isinstance(payload, dict):
                    raise ValueError("schedule body must be a JSON object")
                schedule = Schedule.from_payload(payload)
                if schedule.id != schedule_id:
                    raise ValueError("schedule id must match the request path")
                if not self._audit_mutation(
                    actor,
                    "scheduler.schedule.replace",
                    workspace_id,
                    {"resource": schedule_id.value},
                ):
                    return
                stored_schedule = workflow_reader.put_schedule(workspace_id, schedule)
                self._write_json(HTTPStatus.OK, stored_schedule.to_payload())
                return
            if (
                len(segments) == 5
                and segments[:2] == ("v1", "workspaces")
                and segments[3] == "event-triggers"
            ):
                workflow_reader = self._server().workflow_reader
                if workflow_reader is None:
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "scheduler_unavailable",
                        "workflow scheduler is not configured",
                    )
                    return
                if query:
                    raise ValueError("event trigger replacement does not accept query parameters")
                workspace_id = WorkspaceId(segments[2])
                trigger_id = segments[4]
                if not self._authorize(
                    actor, workspace_id, "scheduler.write", resource_ref=trigger_id
                ):
                    return
                payload = self._read_json()
                if not isinstance(payload, dict):
                    raise ValueError("event trigger body must be a JSON object")
                trigger = EventTriggerDefinition.from_payload(payload)
                if trigger.id.value != trigger_id:
                    raise ValueError("event trigger id must match the request path")
                if not self._audit_mutation(
                    actor,
                    "scheduler.event_trigger.replace",
                    workspace_id,
                    {"resource": trigger_id},
                ):
                    return
                stored_trigger = workflow_reader.put_event_trigger(workspace_id, trigger)
                self._write_json(HTTPStatus.OK, stored_trigger.to_payload())
                return
            if (
                len(segments) == 5
                and segments[:2] == ("v1", "workspaces")
                and segments[3] == "environments"
            ):
                environment_service = self._server().environment_service
                if environment_service is None:
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "environments_unavailable",
                        "environment service is not configured",
                    )
                    return
                if query:
                    raise ValueError("environment replacement does not accept query parameters")
                workspace_id = WorkspaceId(segments[2])
                environment_id = EnvironmentId(segments[4])
                if not self._authorize(
                    actor, workspace_id, "workspace.write", resource_ref=str(environment_id)
                ):
                    return
                environment_current = cast(
                    EnvironmentDefinition, environment_service.get(workspace_id, environment_id)
                )
                if not self._check_if_match(environment_current.to_payload()):
                    return
                replacement_environment = EnvironmentDefinition.from_payload(self._read_json())
                if replacement_environment.id != environment_id:
                    raise ValueError("environment id must match the request path")
                if not self._audit_mutation(
                    actor,
                    "environment.replace",
                    workspace_id,
                    {"resource": str(environment_id)},
                ):
                    return
                environment_result = environment_service.replace(
                    workspace_id, replacement_environment, now=_now()
                ).to_payload()
                self._write_json(HTTPStatus.OK, environment_result, etag=_etag(environment_result))
                return
            if (
                len(segments) == 8
                and segments[:2] == ("v1", "workspaces")
                and segments[3] == "projects"
                and segments[5] == "environments"
                and segments[7] == "bindings"
            ):
                binding_service = self._server().binding_service
                if binding_service is None:
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "environments_unavailable",
                        "binding service is not configured",
                    )
                    return
                workspace_id = WorkspaceId(segments[2])
                project_ref = ProjectId(segments[4])
                environment_id = EnvironmentId(segments[6])
                if not self._authorize(
                    actor, workspace_id, "project.write", resource_ref=str(project_ref)
                ):
                    return
                bindings = ProjectEnvironmentBindings.from_payload(self._read_json())
                if bindings.project_id != project_ref or bindings.environment_id != environment_id:
                    raise ValueError("binding ids must match the request path")
                if not self._audit_mutation(
                    actor,
                    "environment.binding.replace",
                    workspace_id,
                    {"resource": f"{project_ref}/{environment_id}"},
                ):
                    return
                self._write_json(
                    HTTPStatus.OK,
                    binding_service.put(workspace_id, bindings, now=_now()).to_payload(),
                )
                return
            if (
                len(segments) == 6
                and segments[:2] == ("v1", "workspaces")
                and segments[3:5] == ("catalog", "assets")
            ):
                catalog_reader = self._server().catalog_reader
                if catalog_reader is None or not callable(
                    getattr(catalog_reader, "replace_asset", None)
                ):
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "catalog_unavailable",
                        "catalog writer is not configured",
                    )
                    return
                if query:
                    raise ValueError("catalog asset replacement does not accept query parameters")
                workspace_id = WorkspaceId(segments[2])
                if not self._authorize(actor, workspace_id, "workspace.admin"):
                    return
                replacement_asset = CatalogAsset.from_payload(self._read_json())
                asset_id = AssetId(unquote(segments[5]))
                if replacement_asset.id != asset_id:
                    raise ValueError("catalog asset id must match the request path")
                if not self._audit_mutation(
                    actor,
                    "catalog.asset.replace",
                    workspace_id,
                    {"resource": str(replacement_asset.id)},
                ):
                    return
                catalog_asset_stored = catalog_reader.replace_asset(
                    workspace_id, replacement_asset, now=_now()
                )
                self._write_json(HTTPStatus.OK, catalog_asset_stored.to_payload())
                return
            self._method_or_not_found("PUT", segments)
        except Exception as exc:
            self._handle_failure(exc)

    def do_DELETE(self) -> None:  # noqa: N802
        actor = self._authenticate()
        if actor is None:
            return
        try:
            segments, query = self._split()
            if self._server().plugin_routes_enabled:
                plugin_host = self._server().plugin_host
                if isinstance(plugin_host, PluginRouter):
                    resolved = plugin_host.resolve_route("DELETE", urlsplit(self.path).path)
                    if resolved is not None:
                        route, parameters = resolved
                        workspace_value = parameters.get("workspace_id")
                        mapped_permission = {
                            "projects:write": "project.write",
                            "workspaces:write": "workspace.write",
                        }.get(getattr(route, "permission", ""))
                        project_id = parameters.get("project_id")
                        if (
                            workspace_value is None
                            or mapped_permission is None
                            or project_id is None
                        ):
                            self._error(
                                HTTPStatus.FORBIDDEN,
                                "plugin_permission_unmapped",
                                "plugin route permission is not mapped",
                            )
                            return
                        workspace_id = WorkspaceId(workspace_value)
                        if not self._authorize(
                            actor,
                            workspace_id,
                            mapped_permission,
                            resource_ref=project_id,
                        ):
                            return
                        if not self._audit_mutation(
                            actor,
                            "plugin.delete",
                            workspace_id,
                            {"resource": urlsplit(self.path).path},
                        ):
                            return
                        payload = plugin_host.invoke_route(
                            "DELETE", urlsplit(self.path).path, query=query
                        )
                        self._write_json(HTTPStatus.OK, payload)
                        return
            if not self._registered_path(segments):
                self._method_or_not_found("DELETE", segments)
                return
            if (
                len(segments) == 5
                and segments[:2] == ("v1", "workspaces")
                and segments[3] == "projects"
            ):
                if query:
                    raise ValueError("project unregister does not accept query parameters")
                workspace_id = WorkspaceId(segments[2])
                project_id = ProjectId(segments[4])
                if not self._authorize(
                    actor, workspace_id, "project.write", resource_ref=str(project_id)
                ):
                    return
                if (
                    self.headers.get("Content-Length") not in {None, "0"}
                    or self.headers.get("Transfer-Encoding") is not None
                ):
                    raise ValueError("project unregister does not accept a request body")
                if not self._audit_mutation(
                    actor,
                    "project.unregister",
                    workspace_id,
                    {"resource": str(project_id)},
                ):
                    return
                self._server().project_service.unregister(workspace_id, project_id)
                self._write_json(
                    HTTPStatus.OK, {"unregistered": True, "project_id": str(project_id)}
                )
                return
            self._method_or_not_found("DELETE", segments)
        except Exception as exc:
            self._handle_failure(exc)

    def _method_or_not_found(self, method: str, segments: tuple[str, ...]) -> None:
        route_methods = {
            registered_method
            for registered_method, registered_path in CONTROL_PLANE_ROUTES
            if _registered_path_matches(registered_path, segments)
        }
        if route_methods and method not in route_methods:
            self._discard_request_body()
            self._error(
                HTTPStatus.METHOD_NOT_ALLOWED,
                "method_not_allowed",
                f"method {method} is not allowed for this route",
            )
        else:
            self._discard_request_body()
            self._error(HTTPStatus.NOT_FOUND, "not_found", "route does not exist")

    @staticmethod
    def _registered_path(segments: tuple[str, ...]) -> bool:
        return any(
            _registered_path_matches(registered_path, segments)
            for _, registered_path in CONTROL_PLANE_ROUTES
        )


__all__ = (
    "CONTROL_PLANE_ROUTES",
    "PluginDiagnostics",
    "PluginRouter",
    "ControlPlaneAuthenticator",
    "ControlPlaneAuthorizer",
    "ControlPlaneUnavailable",
    "WorkspaceProjectHTTPServer",
    "SqlReader",
)
