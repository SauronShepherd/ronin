"""Authenticated HTTP surface for provider-neutral workspace/project services."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Protocol, cast, runtime_checkable
from urllib.parse import unquote, urlsplit

from studio_core import (
    ProjectId,
    ProjectManifest,
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
from studio_execution import (
    ProjectService,
    WorkspaceService,
    WorkspaceServiceConflict,
    WorkspaceServiceNotFound,
)
from studio_orchestrator import Instant
from studio_security import Actor, Permission, PolicyDecision, PolicyRequirement

_MAX_REQUEST_BYTES = 1024 * 1024
_MAX_LIST_LIMIT = 100
_DEFAULT_LIST_LIMIT = 50
_MAX_CURSOR_BYTES = 256

CONTROL_PLANE_ROUTES = frozenset(
    {
        ("GET", "/v1/workspaces"),
        ("GET", "/v1/workspaces/{workspace_id}"),
        ("PATCH", "/v1/workspaces/{workspace_id}"),
        ("POST", "/v1/workspaces/{workspace_id}/archive"),
        ("GET", "/v1/workspaces/{workspace_id}/projects"),
        ("POST", "/v1/workspaces/{workspace_id}/projects"),
        ("GET", "/v1/workspaces/{workspace_id}/projects/{project_id}"),
        ("PUT", "/v1/workspaces/{workspace_id}/projects/{project_id}"),
        ("DELETE", "/v1/workspaces/{workspace_id}/projects/{project_id}"),
    }
)


class ControlPlaneUnavailable(RuntimeError):
    """Raised by auth/authz adapters when a required dependency is unavailable."""


@runtime_checkable
class ControlPlaneAuthenticator(Protocol):
    def authenticate(self, authorization: str | None) -> Actor | None: ...


@runtime_checkable
class ControlPlaneAuthorizer(Protocol):
    def authorize(self, actor: Actor, requirement: PolicyRequirement) -> PolicyDecision: ...


@runtime_checkable
class WorkflowReader(Protocol):
    def list_workflows(self, workspace_id: WorkspaceId) -> tuple[WorkflowDefinition, ...]: ...

    def get_run(self, workspace_id: WorkspaceId, run_id: WorkflowRunId) -> WorkflowRun | None: ...

    def list_task_runs(
        self, workspace_id: WorkspaceId, run_id: WorkflowRunId
    ) -> tuple[TaskRun, ...]: ...


@runtime_checkable
class WorkflowCanceller(Protocol):
    def cancel_workflow_run(self, workspace_id: WorkspaceId, run_id: WorkflowRunId) -> int: ...


@runtime_checkable
class WorkflowRunner(Protocol):
    def create_workflow_run(
        self,
        workspace_id: WorkspaceId,
        workflow_id: WorkflowId,
        trigger: Trigger,
        *,
        idempotency_key: str,
    ) -> WorkflowRun: ...


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


def _manifest_payload(manifest: ProjectManifest) -> dict[str, object]:
    return manifest.to_data()


def _page(items: list[object], *, limit: int, offset: int) -> tuple[list[object], str | None]:
    selected = items[offset : offset + limit]
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
        request_timeout_seconds: float = 15.0,
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
        self.request_timeout_seconds = request_timeout_seconds
        super().__init__(server_address, _WorkspaceProjectHandler)


class _WorkspaceProjectHandler(BaseHTTPRequestHandler):
    def log_message(self, _format: str, *args: object) -> None:
        del args

    def _server(self) -> WorkspaceProjectHTTPServer:
        return cast(WorkspaceProjectHTTPServer, self.server)

    def _write_json(self, status: HTTPStatus, payload: object) -> None:
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status: HTTPStatus, code: str, message: str) -> None:
        self._write_json(status, {"error": {"code": code, "message": message}})

    def _authenticate(self) -> Actor | None:
        try:
            actor = self._server().authenticator.authenticate(self.headers.get("Authorization"))
        except ControlPlaneUnavailable:
            self._error(
                HTTPStatus.SERVICE_UNAVAILABLE,
                "authentication_unavailable",
                "authentication service unavailable",
            )
            return None
        if actor is None:
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
        self._error(
            HTTPStatus.FORBIDDEN, "forbidden", "required workspace permission is not granted"
        )
        return False

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

    def _handle_failure(self, exc: Exception) -> None:
        if isinstance(exc, WorkspaceServiceNotFound):
            self._error(HTTPStatus.NOT_FOUND, "not_found", "requested resource does not exist")
        elif isinstance(exc, WorkspaceServiceConflict):
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
        actor = self._authenticate()
        if actor is None:
            return
        try:
            segments, query = self._split()
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
                self._write_json(
                    HTTPStatus.OK,
                    _workspace_payload(self._server().workspace_service.get(workspace_id)),
                )
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
                reader = self._server().workflow_reader
                if reader is None:
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "scheduler_unavailable",
                        "workflow scheduler is not configured",
                    )
                    return
                workflows = sorted(
                    reader.list_workflows(workspace_id),
                    key=lambda item: str(item.id),
                )
                selected, next_cursor = _page(list(workflows), limit=limit, offset=offset)
                self._write_json(
                    HTTPStatus.OK,
                    {
                        "items": [cast(WorkflowDefinition, item).to_payload() for item in selected],
                        "next_cursor": next_cursor,
                    },
                )
                return
            if (
                len(segments) == 5
                and segments[:2] == ("v1", "workspaces")
                and segments[3] == "workflow-runs"
            ):
                reader = self._server().workflow_reader
                if reader is None:
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
                workflow_run = reader.get_run(workspace_id, run_id)
                if workflow_run is None:
                    self._error(HTTPStatus.NOT_FOUND, "not_found", "workflow run does not exist")
                    return
                tasks = reader.list_task_runs(workspace_id, run_id)
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
                len(segments) == 5
                and segments[:2] == ("v1", "workspaces")
                and segments[3] == "projects"
            ):
                if query:
                    raise ValueError("project read does not accept query parameters")
                workspace_id = WorkspaceId(segments[2])
                project_id = ProjectId(segments[4])
                if not self._authorize(
                    actor, workspace_id, "project.read", resource_ref=str(project_id)
                ):
                    return
                manifest = self._server().project_service.get(workspace_id, project_id)
                self._write_json(HTTPStatus.OK, _manifest_payload(manifest))
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
            if len(segments) == 3 and segments[:2] == ("v1", "workspaces"):
                if query:
                    raise ValueError("workspace update does not accept query parameters")
                workspace_id = WorkspaceId(segments[2])
                if not self._authorize(actor, workspace_id, "workspace.admin"):
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
                workspace = self._server().workspace_service.update(
                    workspace_id,
                    name=name,
                    description=description,
                    now=_now(),
                )
                self._write_json(HTTPStatus.OK, _workspace_payload(workspace))
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
            if (
                len(segments) == 6
                and segments[:2] == ("v1", "workspaces")
                and segments[3] == "workflows"
                and segments[5] == "runs"
            ):
                runner = self._server().workflow_runner
                if runner is None:
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
                run = runner.create_workflow_run(
                    workspace_id,
                    workflow_id,
                    Trigger.from_payload(payload["trigger"]),
                    idempotency_key=idempotency_key,
                )
                self._write_json(HTTPStatus.CREATED, run.to_payload())
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
                cancelled_jobs = canceller.cancel_workflow_run(workspace_id, run_id)
                self._write_json(
                    HTTPStatus.OK,
                    {"workflow_run_id": run_id.value, "cancelled_jobs": cancelled_jobs},
                )
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
                stored = self._server().project_service.register(workspace_id, manifest, now=_now())
                self._write_json(HTTPStatus.CREATED, _manifest_payload(stored))
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
            if (
                len(segments) == 5
                and segments[:2] == ("v1", "workspaces")
                and segments[3] == "projects"
            ):
                if query:
                    raise ValueError("project replacement does not accept query parameters")
                workspace_id = WorkspaceId(segments[2])
                project_id = ProjectId(segments[4])
                if not self._authorize(
                    actor, workspace_id, "project.write", resource_ref=str(project_id)
                ):
                    return
                payload = self._read_json()
                if not isinstance(payload, dict):
                    raise ValueError("project manifest body must be a JSON object")
                manifest = ProjectManifest.from_data(payload)
                if manifest.project.id != project_id:
                    raise ValueError("project manifest id must match the request path")
                stored = self._server().project_service.replace(workspace_id, manifest, now=_now())
                self._write_json(HTTPStatus.OK, _manifest_payload(stored))
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
                self._server().project_service.unregister(workspace_id, project_id)
                self._write_json(
                    HTTPStatus.OK, {"unregistered": True, "project_id": str(project_id)}
                )
                return
            self._method_or_not_found("DELETE", segments)
        except Exception as exc:
            self._handle_failure(exc)

    def _method_or_not_found(self, method: str, segments: tuple[str, ...]) -> None:
        known = False
        if (
            segments == ("v1", "workspaces")
            or len(segments) == 3
            and segments[:2] == ("v1", "workspaces")
            or (
                len(segments) == 4
                and segments[:2] == ("v1", "workspaces")
                and segments[3] in {"archive", "projects"}
            )
            or (
                len(segments) == 5
                and segments[:2] == ("v1", "workspaces")
                and segments[3] == "projects"
            )
        ):
            known = True
        if known:
            self._error(
                HTTPStatus.METHOD_NOT_ALLOWED,
                "method_not_allowed",
                f"method {method} is not allowed for this route",
            )
        else:
            self._error(HTTPStatus.NOT_FOUND, "not_found", "route does not exist")


__all__ = (
    "CONTROL_PLANE_ROUTES",
    "ControlPlaneAuthenticator",
    "ControlPlaneAuthorizer",
    "ControlPlaneUnavailable",
    "WorkspaceProjectHTTPServer",
)
