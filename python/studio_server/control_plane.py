"""Authenticated HTTP surface for provider-neutral workspace/project services."""

from __future__ import annotations

import base64
import json
import mimetypes
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Protocol, cast, runtime_checkable
from urllib.parse import parse_qs, unquote, urlsplit

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
        ("GET", "/v1/platform/plugins"),
        ("GET", "/v1/platform/capabilities"),
        ("GET", "/v1/platform/ui-manifest"),
        ("GET", "/v1/platform/logs"),
        ("GET", "/v1/platform/traces"),
        ("GET", "/v1/platform/metrics"),
        ("GET", "/v1/workspaces"),
        ("GET", "/v1/workspaces/{workspace_id}"),
        ("PATCH", "/v1/workspaces/{workspace_id}"),
        ("POST", "/v1/workspaces/{workspace_id}/archive"),
        ("GET", "/v1/workspaces/{workspace_id}/projects"),
        ("POST", "/v1/workspaces/{workspace_id}/projects"),
        ("GET", "/v1/workspaces/{workspace_id}/projects/{project_id}"),
        ("PUT", "/v1/workspaces/{workspace_id}/projects/{project_id}"),
        ("DELETE", "/v1/workspaces/{workspace_id}/projects/{project_id}"),
        ("GET", "/v1/workspaces/{workspace_id}/workflows"),
        ("POST", "/v1/workspaces/{workspace_id}/workflows/{workflow_id}/runs"),
        ("GET", "/v1/workspaces/{workspace_id}/workflow-runs/{run_id}"),
        ("POST", "/v1/workspaces/{workspace_id}/workflow-runs/{run_id}/cancel"),
        ("GET", "/v1/ml-studio/labs"),
        ("POST", "/v1/ml-studio/labs"),
        ("POST", "/v1/ml-studio/labs/{lab_id}/quality"),
        ("POST", "/v1/ml-studio/labs/{lab_id}/executions"),
        ("POST", "/v1/ml-studio/labs/{lab_id}/compare"),
        ("POST", "/v1/ml-studio/labs/{lab_id}/search"),
        ("GET", "/v1/ml-studio/models"),
        ("POST", "/v1/ml-studio/models/{model_id}/{version}/promote"),
        ("POST", "/v1/ml-studio/models/{model_id}/{version}/predict"),
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


@runtime_checkable
class PluginDiagnostics(Protocol):
    def diagnostics(self) -> tuple[dict[str, str | None], ...]: ...

    def contribution_diagnostics(self) -> dict[str, object]: ...


@runtime_checkable
class PluginRouter(Protocol):
    def resolve_route(
        self, method: str, path: str
    ) -> tuple[object, dict[str, str]] | None: ...

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
        plugin_host: PluginDiagnostics | None = None,
        plugin_routes_enabled: bool = False,
        studio_root: Path | None = None,
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
        self.plugin_host = plugin_host
        self.plugin_routes_enabled = plugin_routes_enabled
        self.studio_root = studio_root.resolve() if studio_root is not None else None
        self.request_timeout_seconds = request_timeout_seconds
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
        if self._serve_studio():
            return
        actor = self._authenticate()
        if actor is None:
            return
        try:
            segments, query = self._split()
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
                ready = {
                    item["id"] for item in diagnostics if item.get("state") == "ready"
                }
                surfaces = [
                    item for item in cast(list[dict[str, object]], contributions["surfaces"])
                    if str(item.get("plugin_id")) in ready
                ]
                cli = [
                    item for item in cast(list[dict[str, object]], contributions["cli"])
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
                states = {
                    item["id"]: item["state"]
                    for item in plugin_host.diagnostics()
                }
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
            if not self._registered_path(segments):
                self._method_or_not_found("PATCH", segments)
                return
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
                        payload = plugin_host.invoke_route(
                            "POST",
                            urlsplit(self.path).path,
                            query=query,
                            body=body,
                            idempotency_key=self.headers.get("Idempotency-Key"),
                        )
                        self._write_json(HTTPStatus.OK, payload)
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
                        payload = plugin_host.invoke_route(
                            "PUT",
                            urlsplit(self.path).path,
                            query=query,
                            body=self._read_json(),
                        )
                        self._write_json(HTTPStatus.OK, payload)
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
            self._error(
                HTTPStatus.METHOD_NOT_ALLOWED,
                "method_not_allowed",
                f"method {method} is not allowed for this route",
            )
        else:
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
)
