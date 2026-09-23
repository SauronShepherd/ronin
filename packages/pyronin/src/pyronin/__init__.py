"""Official Python SDK for the Ronin control plane."""

from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, OpenerDirector, Request, build_opener

__version__ = "0.0.1a0"

_DEFAULT_MAX_RESPONSE_BYTES = 1024 * 1024
_MAX_CURSOR_BYTES = 4096
_RETRYABLE_STATUS_CODES = frozenset({429, 502, 503, 504})
_RETRYABLE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_INSTANT_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z$")
_JOB_FIELDS = frozenset({"id", "state", "failure_code"})
_EVENT_FIELDS = frozenset(
    {"sequence", "attempt_id", "attempt_sequence", "kind", "message", "occurred_at"}
)
_EVIDENCE_FIELDS = frozenset(
    {
        "version",
        "cell_id",
        "role",
        "digest_algorithm",
        "digest",
        "media_type",
        "size_bytes",
        "availability",
        "reason",
    }
)
_SQL_COLUMN_FIELDS = frozenset({"name", "type"})


class RoninError(Exception):
    """Base exception for the public SDK."""


class TransportError(RoninError):
    """The control plane could not be reached or returned invalid transport data."""


class ProtocolError(RoninError):
    """The control plane returned a payload that violates the SDK contract."""


@dataclass(frozen=True, slots=True)
class APIError(RoninError):
    """The control plane returned a non-success HTTP response."""

    status_code: int
    message: str
    code: str | None = None

    def __str__(self) -> str:
        suffix = f" [{self.code}]" if self.code else ""
        return f"Ronin API error {self.status_code}{suffix}: {self.message}"


class JobState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    SUCCEEDED = "succeeded"
    FAILED = "failed"

    @property
    def terminal(self) -> bool:
        return self in {self.CANCELLED, self.SUCCEEDED, self.FAILED}


class EvidenceAvailability(StrEnum):
    AVAILABLE = "available"
    MISSING = "missing"
    TOMBSTONED = "tombstoned"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class Job:
    id: str
    state: JobState
    failure_code: str | None = None


@dataclass(frozen=True, slots=True)
class JobPage:
    items: tuple[Job, ...]
    next_cursor: str | None = None


@dataclass(frozen=True, slots=True)
class JobEvent:
    sequence: int
    attempt_id: str
    attempt_sequence: int
    kind: str
    message: str
    occurred_at: str


@dataclass(frozen=True, slots=True)
class JobEventPage:
    items: tuple[JobEvent, ...]
    next_since: str


@dataclass(frozen=True, slots=True)
class EvidenceReference:
    version: int
    cell_id: str | None
    role: str
    digest_algorithm: str | None
    digest: str | None
    media_type: str | None
    size_bytes: int | None
    availability: EvidenceAvailability
    reason: str | None = None

    @property
    def portable_identity(self) -> tuple[str, str, str, str | None, int] | None:
        if self.digest_algorithm is None or self.digest is None or self.size_bytes is None:
            return None
        return (self.role, self.digest_algorithm, self.digest, self.media_type, self.size_bytes)


@dataclass(frozen=True, slots=True)
class SqlColumn:
    name: str
    type_name: str


@dataclass(frozen=True, slots=True)
class SqlResult:
    columns: tuple[SqlColumn, ...]
    rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True, slots=True)
class CatalogAsset:
    id: str
    kind: str
    name: str
    tags: tuple[str, ...] = ()
    classifications: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CatalogLineageEdge:
    source: Mapping[str, object]
    target: Mapping[str, object]
    operation: str
    mode: str
    execution_ref: str | None
    column_mappings: tuple[Mapping[str, object], ...] = ()


@dataclass(frozen=True, slots=True)
class GlossaryTerm:
    id: str
    version: str
    name: str
    definition: str
    owner: str
    references: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class OwnershipMetadata:
    version: int
    owner_ref: str
    steward_refs: tuple[str, ...] = ()
    domain: str | None = None
    lifecycle: str = "active"


@dataclass(frozen=True, slots=True)
class SensitivityMetadata:
    version: int
    explicit: tuple[str, ...] = ()
    inherited: tuple[str, ...] = ()
    inherited_from: tuple[str, ...] = ()

    @property
    def effective_level(self) -> str | None:
        levels = [
            label
            for label in (*self.explicit, *self.inherited)
            if label in {"public", "internal", "confidential", "restricted"}
        ]
        return (
            max(levels, key=("public", "internal", "confidential", "restricted").index)
            if levels
            else None
        )


@dataclass(frozen=True, slots=True)
class StreamingHealth:
    stream_id: str
    checkpoint_digest: str
    partitions: int
    lag: Mapping[str, int]
    total_lag: int
    healthy: bool


@dataclass(frozen=True, slots=True)
class SemanticQueryResult:
    columns: tuple[SqlColumn, ...]
    rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True, slots=True)
class PluginSurface:
    id: str
    plugin_id: str
    namespace: str
    command: str
    operation_id: str

    capability: str
    permission: str
    transport: str
    api_version: str
    path: str
    method: str


@dataclass(frozen=True, slots=True)
class Workspace:
    id: str
    name: str
    status: str = "active"
    version: int | None = None


@dataclass(frozen=True, slots=True)
class Project:
    id: str
    name: str
    version: int | None = None
    status: str = "active"


@dataclass(frozen=True, slots=True)
class WorkspacePage:
    items: tuple[Workspace, ...]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class ProjectPage:
    items: tuple[Project, ...]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class Environment:
    id: str
    name: str
    state: str = "active"
    description: str | None = None


@dataclass(frozen=True, slots=True)
class DeploymentBinding:
    kind: str
    source_ref: str
    target_ref: str

    def __post_init__(self) -> None:
        if not all(
            isinstance(value, str) and value.strip()
            for value in (self.kind, self.source_ref, self.target_ref)
        ):
            raise ValueError("binding fields must be non-empty strings")
        expected = {
            "connection": "connection",
            "secret": "secret",
            "runtime": "runtime",
            "identity": "identity",
            "notification": "notification",
            "model_provider": "model-provider",
            "storage": "storage",
            "endpoint": "endpoint",
        }.get(self.kind)
        if expected is None:
            raise ValueError("unsupported binding kind")
        folded = self.target_ref.casefold()
        if any(term in folded for term in ("password=", "token=", "secret=", "api_key=")):
            raise ValueError("binding target must not contain credential material")
        parsed = urlsplit(self.target_ref)
        if parsed.scheme != expected or parsed.username is not None or parsed.password is not None:
            raise ValueError("binding target has an invalid or credential-bearing scheme")
        if parsed.query or parsed.fragment or (not parsed.netloc and not parsed.path):
            raise ValueError("binding target must identify a credential-free resource")


@dataclass(frozen=True, slots=True)
class ProjectEnvironmentBindings:
    project_id: str
    environment_id: str
    bindings: tuple[DeploymentBinding, ...]


@dataclass(frozen=True, slots=True)
class Principal:
    id: str
    kind: str
    display_name: str
    issuer: str
    subject: str
    email: str | None = None
    active: bool = True


@dataclass(frozen=True, slots=True)
class Group:
    id: str
    name: str


def _parse_principal(payload: object) -> Principal:
    item = _parse_resource(payload, "principal")
    fields = ("id", "kind", "display_name", "issuer", "subject")
    if not all(isinstance(item.get(field), str) and item[field] for field in fields):
        raise ProtocolError("principal response has invalid identity")
    email = item.get("email")
    if email is not None and not isinstance(email, str):
        raise ProtocolError("principal response has invalid email")
    return Principal(*(item[field] for field in fields), email, bool(item.get("active", True)))


def _parse_group(payload: object) -> Group:
    item = _parse_resource(payload, "group")
    if not isinstance(item.get("id"), str) or not isinstance(item.get("name"), str):
        raise ProtocolError("group response has invalid identity")
    return Group(item["id"], item["name"])


@dataclass(frozen=True, slots=True)
class RoleBinding:
    workspace_id: str
    subject_kind: str
    subject_id: str
    role: str


def _parse_role_binding(payload: object) -> RoleBinding:
    item = _parse_resource(payload, "role_binding")
    fields = ("workspace_id", "subject_kind", "subject_id", "role")
    if not all(isinstance(item.get(field), str) and item[field] for field in fields):
        raise ProtocolError("role binding response has invalid identity")
    return RoleBinding(*(item[field] for field in fields))


def _parse_resource(payload: object, kind: str) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise ProtocolError(f"{kind} response must be an object")
    resource = payload.get(kind)
    if resource is not None:
        if not isinstance(resource, dict):
            raise ProtocolError(f"{kind} response has invalid resource")
        return resource
    return payload


def _parse_workspace(payload: object) -> Workspace:
    item = _parse_resource(payload, "workspace")
    if not isinstance(item.get("id"), str) or not isinstance(item.get("name"), str):
        raise ProtocolError("workspace response has invalid identity")
    return Workspace(
        item["id"], item["name"], str(item.get("status", "active")), item.get("version")
    )


def _parse_project(payload: object) -> Project:
    item = _parse_resource(payload, "project")
    if not isinstance(item.get("id"), str) or not isinstance(item.get("name"), str):
        raise ProtocolError("project response has invalid identity")
    return Project(item["id"], item["name"], item.get("version"), str(item.get("status", "active")))


def _parse_environment(payload: object) -> Environment:
    item = _parse_resource(payload, "environment")
    if not isinstance(item.get("id"), str) or not isinstance(item.get("name"), str):
        raise ProtocolError("environment response has invalid identity")
    return Environment(
        item["id"],
        item["name"],
        str(item.get("state", item.get("status", "active"))),
        item.get("description") if isinstance(item.get("description"), str) else None,
    )


def _parse_bindings(payload: object) -> ProjectEnvironmentBindings:
    if not isinstance(payload, dict):
        raise ProtocolError("bindings response must be an object")
    project_id = payload.get("project_id")
    environment_id = payload.get("environment_id")
    raw = payload.get("bindings")
    if not isinstance(project_id, str) or not project_id.strip():
        raise ProtocolError("bindings response has invalid project_id")
    if not isinstance(environment_id, str) or not environment_id.strip():
        raise ProtocolError("bindings response has invalid environment_id")
    if not isinstance(raw, list):
        raise ProtocolError("bindings response must contain a bindings array")
    parsed: list[DeploymentBinding] = []
    for item in raw:
        if not isinstance(item, dict) or not all(
            isinstance(item.get(key), str) and item[key].strip()
            for key in ("kind", "source_ref", "target_ref")
        ):
            raise ProtocolError("binding response has invalid fields")
        parsed.append(DeploymentBinding(item["kind"], item["source_ref"], item["target_ref"]))
    return ProjectEnvironmentBindings(project_id, environment_id, tuple(parsed))


@dataclass(frozen=True, slots=True)
class PluginInfo:
    id: str
    version: str
    state: str
    error: str | None = None


@dataclass(frozen=True, slots=True)
class PluginCliContribution:
    id: str
    namespace: str
    command: str
    operation_id: str
    options: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PluginClientOperation:
    id: str
    operation_id: str
    transport: str
    path: str
    method: str


@dataclass(frozen=True, slots=True)
class PlatformPlugins:
    items: tuple[PluginInfo, ...]
    surfaces: tuple[PluginSurface, ...]
    cli: tuple[PluginCliContribution, ...] = ()
    client_operations: tuple[PluginClientOperation, ...] = ()


class PluginClient:
    """Namespaced transport facade backed by server-advertised surfaces."""

    def __init__(self, client: Ronin, namespace: str) -> None:
        self._client = client
        self._namespace = namespace

    def invoke(
        self,
        operation_id: str,
        *,
        payload: Mapping[str, object] | None = None,
        path_params: Mapping[str, str] | None = None,
    ) -> object:
        surface = next(
            (
                item
                for item in self._client.platform_plugins().surfaces
                if item.namespace == self._namespace and item.operation_id == operation_id
            ),
            None,
        )
        if surface is None:
            raise ValueError(f"operation is not advertised for plugin namespace: {operation_id}")
        if surface.transport != "http" or not surface.path:
            raise ProtocolError(f"operation cannot be invoked over HTTP: {operation_id}")
        path = surface.path
        for key, value in (path_params or {}).items():
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"path parameter {key} must be non-empty")
            path = path.replace("{" + key + "}", quote(value, safe=""))
        if "{" in path or "}" in path:
            raise ValueError(f"missing path parameter for operation: {operation_id}")
        return self._client._transport.request(
            surface.method,
            path,
            payload=payload,
        )


class Transport(Protocol):
    def request(
        self,
        method: str,
        path: str,
        *,
        payload: Mapping[str, object] | None = None,
        headers: Mapping[str, str] | None = None,
        query: Mapping[str, str] | None = None,
    ) -> object: ...


class _Readable(Protocol):
    def read(self, size: int = -1) -> bytes: ...


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(
        self,
        req: Request,
        fp: object,
        code: int,
        msg: str,
        headers: object,
        newurl: str,
    ) -> None:
        del req, fp, code, msg, headers, newurl
        return


def _is_loopback_host(hostname: str | None) -> bool:
    if hostname is None:
        return False
    if hostname.casefold() == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def _read_bounded(stream: _Readable, max_bytes: int) -> bytes:
    body = stream.read(max_bytes + 1)
    if len(body) > max_bytes:
        raise TransportError("Ronin response exceeded configured byte limit")
    return body


def _api_error(body: bytes) -> tuple[str | None, str]:
    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, "request failed"
    if not isinstance(payload, dict) or set(payload) != {"error"}:
        return None, "request failed"
    error = payload.get("error")
    if not isinstance(error, dict) or set(error) != {"code", "message"}:
        return None, "request failed"
    code = error.get("code")
    message = error.get("message")
    if (
        not isinstance(code, str)
        or not code
        or len(code) > 128
        or not isinstance(message, str)
        or not message
    ):
        return None, "request failed"
    return code, message


def _request_is_retry_safe(method: str, headers: Mapping[str, str]) -> bool:
    upper = method.upper()
    if upper in _RETRYABLE_METHODS:
        return True
    if upper == "POST":
        return any(key.casefold() == "idempotency-key" for key in headers)
    return False


def _validate_cursor(value: str | None, *, name: str) -> None:
    if value is not None and (
        not value or value != value.strip() or len(value.encode("utf-8")) > _MAX_CURSOR_BYTES
    ):
        raise ValueError(f"{name} must be non-empty, trimmed, and within the byte limit")


def _parse_cursor(value: object, *, name: str, nullable: bool) -> str | None:
    if value is None and nullable:
        return None
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value.encode("utf-8")) > _MAX_CURSOR_BYTES
    ):
        raise ProtocolError(f"{name} must be a bounded non-empty string")
    return value


@dataclass(frozen=True, slots=True)
class HTTPTransport:
    base_url: str
    token: str | None = None
    timeout: float = 30.0
    max_response_bytes: int = _DEFAULT_MAX_RESPONSE_BYTES
    allow_insecure_localhost: bool = False
    max_retries: int = 2
    backoff_seconds: float = 0.1
    _opener: OpenerDirector = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not self.base_url.strip() or self.base_url.strip() != self.base_url:
            raise ValueError("base_url must be non-empty and trimmed")
        parsed = urlsplit(self.base_url)
        if parsed.scheme not in {"http", "https"} or parsed.hostname is None:
            raise ValueError("base_url must be an absolute http(s) URL")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("base_url must not contain credentials")
        if parsed.query or parsed.fragment:
            raise ValueError("base_url must not contain query or fragment components")
        if self.timeout <= 0:
            raise ValueError("timeout must be positive")
        if self.max_response_bytes < 1:
            raise ValueError("max_response_bytes must be positive")
        if self.max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        if self.backoff_seconds < 0:
            raise ValueError("backoff_seconds must be non-negative")
        if self.token is not None:
            if not self.token or self.token.strip() != self.token:
                raise ValueError("token must be non-empty and trimmed when supplied")
            insecure_loopback = (
                parsed.scheme == "http"
                and self.allow_insecure_localhost
                and _is_loopback_host(parsed.hostname)
            )
            if parsed.scheme != "https" and not insecure_loopback:
                raise ValueError(
                    "authenticated HTTP requires HTTPS; insecure transport is allowed only for "
                    "explicit loopback development"
                )
        object.__setattr__(self, "_opener", build_opener(_RejectRedirects()))

    def _sleep_before_retry(self, attempt: int) -> None:
        if self.backoff_seconds:
            time.sleep(self.backoff_seconds * (2**attempt))

    def request(
        self,
        method: str,
        path: str,
        *,
        payload: Mapping[str, object] | None = None,
        headers: Mapping[str, str] | None = None,
        query: Mapping[str, str] | None = None,
    ) -> object:
        if not path.startswith("/") or path.startswith("//"):
            raise ValueError("path must be an origin-relative absolute path")
        url = self.base_url.rstrip("/") + path
        if query:
            url += "?" + urlencode(query)
        request_headers = {"Accept": "application/json"}
        if headers:
            request_headers.update(headers)
        if self.token:
            request_headers["Authorization"] = f"Bearer {self.token}"
        data = None
        if payload is not None:
            request_headers["Content-Type"] = "application/json"
            data = json.dumps(dict(payload), separators=(",", ":")).encode("utf-8")
        retry_safe = _request_is_retry_safe(method, request_headers)

        for attempt in range(self.max_retries + 1):
            request = Request(url, data=data, headers=request_headers, method=method)  # noqa: S310
            try:
                with self._opener.open(request, timeout=self.timeout) as response:  # noqa: S310
                    body = _read_bounded(response, self.max_response_bytes)
            except HTTPError as exc:
                try:
                    error_body = _read_bounded(exc, self.max_response_bytes)
                except TransportError as limit_error:
                    raise APIError(
                        exc.code,
                        "error response exceeded configured byte limit",
                    ) from limit_error
                if (
                    retry_safe
                    and exc.code in _RETRYABLE_STATUS_CODES
                    and attempt < self.max_retries
                ):
                    self._sleep_before_retry(attempt)
                    continue
                code, message = _api_error(error_body)
                raise APIError(exc.code, message, code) from exc
            except URLError as exc:
                if retry_safe and attempt < self.max_retries:
                    self._sleep_before_retry(attempt)
                    continue
                raise TransportError("Ronin endpoint unavailable") from exc
            if not body:
                return None
            try:
                return json.loads(body)
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise TransportError("Ronin endpoint returned invalid JSON") from exc
        raise AssertionError("unreachable retry loop")


class Ronin:
    """Synchronous client for Ronin job-control APIs."""

    def __init__(
        self,
        base_url: str | None = None,
        *,
        token: str | None = None,
        transport: Transport | None = None,
    ) -> None:
        if transport is not None and base_url is not None:
            raise ValueError("base_url and transport are mutually exclusive")
        if transport is None:
            if base_url is None:
                raise ValueError("base_url is required when transport is not supplied")
            transport = HTTPTransport(base_url, token)
        self._transport = transport

    def list_workspaces(self, *, limit: int = 100) -> tuple[Workspace, ...]:
        return self.list_workspaces_page(limit=limit).items

    def list_workspaces_page(self, *, limit: int = 100, cursor: str | None = None) -> WorkspacePage:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        if cursor is not None and not cursor.strip():
            raise ValueError("cursor must be non-empty when provided")
        query = {"limit": str(limit)}
        if cursor is not None:
            query["cursor"] = cursor
        payload = self._transport.request("GET", "/v1/workspaces", query=query)
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            raise ProtocolError("workspaces response must contain an items array")
        next_cursor = payload.get("next_cursor")
        if next_cursor is not None and not isinstance(next_cursor, str):
            raise ProtocolError("workspaces response has invalid next_cursor")
        return WorkspacePage(
            tuple(_parse_workspace(item) for item in payload["items"]), next_cursor
        )

    def create_workspace(
        self,
        workspace_id: str,
        *,
        name: str,
        description: str | None = None,
        idempotency_key: str,
    ) -> Workspace:
        if not workspace_id.strip() or not name.strip() or not idempotency_key.strip():
            raise ValueError("workspace_id, name and idempotency_key must be non-empty")
        payload = {"id": workspace_id, "name": name, "description": description}
        return _parse_workspace(
            self._transport.request(
                "POST",
                "/v1/workspaces",
                payload=payload,
                headers={"Idempotency-Key": idempotency_key},
            )
        )

    def get_workspace(self, workspace_id: str) -> Workspace:
        if not workspace_id.strip():
            raise ValueError("workspace_id must be non-empty")
        return _parse_workspace(
            self._transport.request("GET", f"/v1/workspaces/{quote(workspace_id, safe='')}")
        )

    def list_projects(self, workspace_id: str, *, limit: int = 100) -> tuple[Project, ...]:
        return self.list_projects_page(workspace_id, limit=limit).items

    def list_projects_page(
        self, workspace_id: str, *, limit: int = 100, cursor: str | None = None
    ) -> ProjectPage:
        if not workspace_id.strip():
            raise ValueError("workspace_id must be non-empty")
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        if cursor is not None and not cursor.strip():
            raise ValueError("cursor must be non-empty when provided")
        query = {"limit": str(limit)}
        if cursor is not None:
            query["cursor"] = cursor
        payload = self._transport.request(
            "GET",
            f"/v1/workspaces/{quote(workspace_id, safe='')}/projects",
            query=query,
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            raise ProtocolError("projects response must contain an items array")
        next_cursor = payload.get("next_cursor")
        if next_cursor is not None and not isinstance(next_cursor, str):
            raise ProtocolError("projects response has invalid next_cursor")
        return ProjectPage(tuple(_parse_project(item) for item in payload["items"]), next_cursor)

    def get_project(self, workspace_id: str, project_id: str) -> Project:
        if not workspace_id.strip() or not project_id.strip():
            raise ValueError("workspace_id and project_id must be non-empty")
        return _parse_project(
            self._transport.request(
                "GET",
                f"/v1/workspaces/{quote(workspace_id, safe='')}/projects/"
                f"{quote(project_id, safe='')}",
            )
        )

    def archive_workspace(self, workspace_id: str) -> Workspace:
        if not workspace_id.strip():
            raise ValueError("workspace_id must be non-empty")
        return _parse_workspace(
            self._transport.request(
                "POST", f"/v1/workspaces/{quote(workspace_id, safe='')}/archive"
            )
        )

    def update_workspace(
        self,
        workspace_id: str,
        *,
        name: str,
        description: str | None = None,
        if_match: str | None = None,
    ) -> Workspace:
        if not workspace_id.strip() or not name.strip():
            raise ValueError("workspace_id and name must be non-empty")
        payload: dict[str, object] = {"name": name}
        if description is not None:
            payload["description"] = description
        headers = {"If-Match": if_match} if if_match else None
        return _parse_workspace(
            self._transport.request(
                "PATCH",
                f"/v1/workspaces/{quote(workspace_id, safe='')}",
                payload=payload,
                headers=headers,
            )
        )

    def create_project(
        self,
        workspace_id: str,
        manifest: Mapping[str, object],
        *,
        idempotency_key: str | None = None,
    ) -> Project:
        if not workspace_id.strip():
            raise ValueError("workspace_id must be non-empty")
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
        return _parse_project(
            self._transport.request(
                "POST",
                f"/v1/workspaces/{quote(workspace_id, safe='')}/projects",
                payload=dict(manifest),
                headers=headers,
            )
        )

    def update_project(
        self,
        workspace_id: str,
        project_id: str,
        manifest: Mapping[str, object],
        *,
        if_match: str | None = None,
    ) -> Project:
        if not workspace_id.strip() or not project_id.strip():
            raise ValueError("workspace_id and project_id must be non-empty")
        headers = {"If-Match": if_match} if if_match else None
        return _parse_project(
            self._transport.request(
                "PUT",
                f"/v1/workspaces/{quote(workspace_id, safe='')}/projects/"
                f"{quote(project_id, safe='')}",
                payload=dict(manifest),
                headers=headers,
            )
        )

    def delete_project(self, workspace_id: str, project_id: str) -> bool:
        if not workspace_id.strip() or not project_id.strip():
            raise ValueError("workspace_id and project_id must be non-empty")
        payload = self._transport.request(
            "DELETE",
            f"/v1/workspaces/{quote(workspace_id, safe='')}/projects/{quote(project_id, safe='')}",
        )
        return isinstance(payload, dict) and payload.get("unregistered") is True

    def archive_project(self, workspace_id: str, project_id: str) -> bool:
        if not workspace_id.strip() or not project_id.strip():
            raise ValueError("workspace_id and project_id must be non-empty")
        payload = self._transport.request(
            "POST",
            f"/v1/workspaces/{quote(workspace_id, safe='')}/projects/"
            f"{quote(project_id, safe='')}/archive",
        )
        return isinstance(payload, dict) and payload.get("archived") is True

    def export_project_bundle_manifest(
        self, workspace_id: str, project_id: str
    ) -> Mapping[str, object]:
        """Return the canonical, portable project manifest used by Bundle export."""
        if not workspace_id.strip() or not project_id.strip():
            raise ValueError("workspace_id and project_id must be non-empty")
        payload = self._transport.request(
            "GET",
            f"/v1/workspaces/{quote(workspace_id, safe='')}/projects/"
            f"{quote(project_id, safe='')}/bundle",
        )
        if not isinstance(payload, dict) or payload.get("schema") != "ronin.project/v1":
            raise ProtocolError("project Bundle response must be a canonical project manifest")
        return payload

    def export_project_bundle_archive(self, workspace_id: str, project_id: str) -> bytes:
        """Download and verify the deterministic project Bundle archive."""
        if not workspace_id.strip() or not project_id.strip():
            raise ValueError("workspace_id and project_id must be non-empty")
        payload = self._transport.request(
            "GET",
            f"/v1/workspaces/{quote(workspace_id, safe='')}/projects/"
            f"{quote(project_id, safe='')}/bundle/archive",
        )
        if (
            not isinstance(payload, dict)
            or payload.get("media_type") != "application/vnd.ronin.bundle+zip"
        ):
            raise ProtocolError("project Bundle archive response has invalid media type")
        encoded, digest, size = (
            payload.get("content_base64"),
            payload.get("digest"),
            payload.get("size_bytes"),
        )
        if not isinstance(encoded, str) or not isinstance(digest, str) or not isinstance(size, int):
            raise ProtocolError("project Bundle archive response has invalid fields")
        try:
            archive = base64.b64decode(encoded, validate=True)
        except (ValueError, TypeError) as exc:
            raise ProtocolError("project Bundle archive content is not valid base64") from exc
        if len(archive) != size or hashlib.sha256(archive).hexdigest() != digest:
            raise ProtocolError("project Bundle archive digest does not match content")
        return archive

    def import_project_bundle_archive(
        self,
        workspace_id: str,
        project_id: str,
        archive: bytes,
        *,
        idempotency_key: str,
    ) -> Mapping[str, object]:
        """Verify and import a deterministic project Bundle archive."""
        if not workspace_id.strip() or not project_id.strip() or not idempotency_key.strip():
            raise ValueError("workspace_id, project_id, and idempotency_key must be non-empty")
        if not isinstance(archive, bytes) or not archive:
            raise ValueError("archive must be non-empty bytes")
        payload = self._transport.request(
            "POST",
            f"/v1/workspaces/{quote(workspace_id, safe='')}/projects/"
            f"{quote(project_id, safe='')}/bundle/import",
            payload={"content_base64": base64.b64encode(archive).decode("ascii")},
            headers={"Idempotency-Key": idempotency_key},
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("project"), dict):
            raise ProtocolError("project Bundle import response must contain a project object")
        return payload

    def list_pipelines(
        self, workspace_id: str, project_id: str
    ) -> tuple[Mapping[str, object], ...]:
        if not workspace_id.strip() or not project_id.strip():
            raise ValueError("workspace_id and project_id must be non-empty")
        payload = self._transport.request(
            "GET",
            f"/v1/workspaces/{quote(workspace_id, safe='')}/projects/"
            f"{quote(project_id, safe='')}/pipelines",
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            raise ProtocolError("pipelines response must contain an items array")
        if not all(isinstance(item, dict) for item in payload["items"]):
            raise ProtocolError("pipeline items must be objects")
        return tuple(payload["items"])

    def list_pipeline_revisions(
        self, workspace_id: str, project_id: str, pipeline_id: str
    ) -> tuple[Mapping[str, object], ...]:
        """List immutable Data Engineering pipeline revisions."""
        if not workspace_id.strip() or not project_id.strip() or not pipeline_id.strip():
            raise ValueError("workspace_id, project_id, and pipeline_id must be non-empty")
        payload = self._transport.request(
            "GET",
            f"/v1/workspaces/{quote(workspace_id, safe='')}/projects/{quote(project_id, safe='')}"
            f"/pipelines/{quote(pipeline_id, safe='')}/revisions",
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            raise ProtocolError("pipeline revisions response must contain an items array")
        if not all(isinstance(item, dict) for item in payload["items"]):
            raise ProtocolError("pipeline revisions items must be objects")
        return tuple(payload["items"])

    def list_notebooks(
        self, workspace_id: str, project_id: str
    ) -> tuple[Mapping[str, object], ...]:
        if not workspace_id.strip() or not project_id.strip():
            raise ValueError("workspace_id and project_id must be non-empty")
        payload = self._transport.request(
            "GET",
            f"/v1/workspaces/{quote(workspace_id, safe='')}/projects/"
            f"{quote(project_id, safe='')}/notebooks",
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            raise ProtocolError("notebooks response must contain an items array")
        if not all(isinstance(item, dict) for item in payload["items"]):
            raise ProtocolError("notebook items must be objects")
        return tuple(payload["items"])

    def get_notebook(
        self, workspace_id: str, project_id: str, notebook_id: str
    ) -> Mapping[str, object]:
        if not workspace_id.strip() or not project_id.strip() or not notebook_id.strip():
            raise ValueError("workspace_id, project_id, and notebook_id must be non-empty")
        payload = self._transport.request(
            "GET",
            f"/v1/workspaces/{quote(workspace_id, safe='')}/projects/"
            f"{quote(project_id, safe='')}/notebooks/{quote(notebook_id, safe='')}",
        )
        if not isinstance(payload, dict):
            raise ProtocolError("notebook response must be an object")
        return payload

    def create_notebook(
        self, workspace_id: str, project_id: str, payload: Mapping[str, object]
    ) -> Mapping[str, object]:
        if not workspace_id.strip() or not project_id.strip():
            raise ValueError("workspace_id and project_id must be non-empty")
        result = self._transport.request(
            "POST",
            f"/v1/workspaces/{quote(workspace_id, safe='')}/projects/"
            f"{quote(project_id, safe='')}/notebooks",
            payload=payload,
        )
        if not isinstance(result, dict):
            raise ProtocolError("notebook response must be an object")
        return result

    def save_notebook(
        self, workspace_id: str, project_id: str, notebook_id: str, payload: Mapping[str, object]
    ) -> Mapping[str, object]:
        if not workspace_id.strip() or not project_id.strip() or not notebook_id.strip():
            raise ValueError("workspace_id, project_id, and notebook_id must be non-empty")
        result = self._transport.request(
            "PUT",
            f"/v1/workspaces/{quote(workspace_id, safe='')}/projects/"
            f"{quote(project_id, safe='')}/notebooks/{quote(notebook_id, safe='')}",
            payload=payload,
        )
        if not isinstance(result, dict):
            raise ProtocolError("notebook response must be an object")
        return result

    def archive_notebook(
        self, workspace_id: str, project_id: str, notebook_id: str, expected_revision: int
    ) -> Mapping[str, object]:
        if isinstance(expected_revision, bool) or expected_revision < 1:
            raise ValueError("expected_revision must be positive")
        result = self._transport.request(
            "POST",
            f"/v1/workspaces/{quote(workspace_id, safe='')}/projects/"
            f"{quote(project_id, safe='')}/notebooks/{quote(notebook_id, safe='')}/archive",
            payload={"expected_revision": expected_revision},
        )
        if not isinstance(result, dict):
            raise ProtocolError("notebook response must be an object")
        return result

    def delete_notebook(
        self, workspace_id: str, project_id: str, notebook_id: str, expected_revision: int
    ) -> Mapping[str, object]:
        if isinstance(expected_revision, bool) or expected_revision < 1:
            raise ValueError("expected_revision must be positive")
        result = self._transport.request(
            "DELETE",
            f"/v1/workspaces/{quote(workspace_id, safe='')}/projects/"
            f"{quote(project_id, safe='')}/notebooks/{quote(notebook_id, safe='')}",
            headers={"If-Match": str(expected_revision)},
        )
        if not isinstance(result, dict):
            raise ProtocolError("notebook deletion response must be an object")
        return result

    def preview_schedule_next_runs(
        self,
        workspace_id: str,
        schedule_id: str,
        after: str,
        *,
        count: int = 10,
    ) -> tuple[str, ...]:
        """Return bounded future fire times for a scheduler schedule."""
        if not all(
            isinstance(value, str) and value.strip() for value in (workspace_id, schedule_id, after)
        ):
            raise ValueError("workspace_id, schedule_id, and after must be non-empty")
        if isinstance(count, bool) or count < 1 or count > 1000:
            raise ValueError("count must be between 1 and 1000")
        result = self._transport.request(
            "GET",
            f"/v1/workspaces/{quote(workspace_id, safe='')}/schedules/"
            f"{quote(schedule_id, safe='')}/next-runs",
            query={"after": after, "count": str(count)},
        )
        if not isinstance(result, dict) or not isinstance(result.get("items"), list):
            raise ProtocolError("next-runs response must contain an items array")
        if not all(isinstance(item, str) for item in result["items"]):
            raise ProtocolError("next-runs items must be strings")
        return tuple(result["items"])

    def list_schedules(
        self, workspace_id: str, *, limit: int = 100
    ) -> tuple[Mapping[str, object], ...]:
        if not workspace_id.strip():
            raise ValueError("workspace_id must be non-empty")
        if isinstance(limit, bool) or limit < 1 or limit > 100:
            raise ValueError("limit must be between 1 and 100")
        result = self._transport.request(
            "GET",
            f"/v1/workspaces/{quote(workspace_id, safe='')}/schedules",
            query={"limit": str(limit)},
        )
        if not isinstance(result, dict) or not isinstance(result.get("items"), list):
            raise ProtocolError("schedule response must contain an items array")
        if not all(isinstance(item, dict) for item in result["items"]):
            raise ProtocolError("schedule items must be objects")
        return tuple(result["items"])

    def list_workflows(
        self, workspace_id: str, *, limit: int = 100
    ) -> tuple[Mapping[str, object], ...]:
        if not workspace_id.strip():
            raise ValueError("workspace_id must be non-empty")
        if isinstance(limit, bool) or limit < 1 or limit > 100:
            raise ValueError("limit must be between 1 and 100")
        result = self._transport.request(
            "GET",
            f"/v1/workspaces/{quote(workspace_id, safe='')}/workflows",
            query={"limit": str(limit)},
        )
        if not isinstance(result, dict) or not isinstance(result.get("items"), list):
            raise ProtocolError("workflow response must contain an items array")
        if not all(isinstance(item, dict) for item in result["items"]):
            raise ProtocolError("workflow items must be objects")
        return tuple(result["items"])

    def get_schedule(self, workspace_id: str, schedule_id: str) -> Mapping[str, object]:
        if not workspace_id.strip() or not schedule_id.strip():
            raise ValueError("workspace_id and schedule_id must be non-empty")
        result = self._transport.request(
            "GET",
            f"/v1/workspaces/{quote(workspace_id, safe='')}/schedules/"
            f"{quote(schedule_id, safe='')}",
        )
        if not isinstance(result, dict):
            raise ProtocolError("schedule response must be an object")
        return result

    def replace_schedule(
        self, workspace_id: str, schedule_id: str, schedule: Mapping[str, object]
    ) -> Mapping[str, object]:
        if not workspace_id.strip() or not schedule_id.strip():
            raise ValueError("workspace_id and schedule_id must be non-empty")
        if not isinstance(schedule, Mapping):
            raise ValueError("schedule must be an object")
        result = self._transport.request(
            "PUT",
            f"/v1/workspaces/{quote(workspace_id, safe='')}/schedules/"
            f"{quote(schedule_id, safe='')}",
            payload=dict(schedule),
        )
        if not isinstance(result, dict):
            raise ProtocolError("schedule response must be an object")
        return result

    def list_schedule_history(
        self, workspace_id: str, schedule_id: str, *, limit: int = 100
    ) -> tuple[Mapping[str, object], ...]:
        """Return bounded durable fire history for a scheduler schedule."""
        if not workspace_id.strip() or not schedule_id.strip():
            raise ValueError("workspace_id and schedule_id must be non-empty")
        if isinstance(limit, bool) or limit < 1 or limit > 1000:
            raise ValueError("limit must be between 1 and 1000")
        result = self._transport.request(
            "GET",
            f"/v1/workspaces/{quote(workspace_id, safe='')}/schedules/"
            f"{quote(schedule_id, safe='')}/history",
            query={"limit": str(limit)},
        )
        if not isinstance(result, dict) or not isinstance(result.get("items"), list):
            raise ProtocolError("schedule history response must contain an items array")
        items = result["items"]
        if not all(isinstance(item, dict) for item in items):
            raise ProtocolError("schedule history items must be objects")
        return tuple(items)

    def list_event_triggers(
        self, workspace_id: str, *, limit: int = 100
    ) -> tuple[Mapping[str, object], ...]:
        """List bounded event-trigger definitions for a workspace."""
        if not workspace_id.strip():
            raise ValueError("workspace_id must be non-empty")
        if isinstance(limit, bool) or limit < 1 or limit > 100:
            raise ValueError("limit must be between 1 and 100")
        result = self._transport.request(
            "GET",
            f"/v1/workspaces/{quote(workspace_id, safe='')}/event-triggers",
            query={"limit": str(limit)},
        )
        if not isinstance(result, dict) or not isinstance(result.get("items"), list):
            raise ProtocolError("event trigger response must contain an items array")
        if not all(isinstance(item, dict) for item in result["items"]):
            raise ProtocolError("event trigger items must be objects")
        return tuple(result["items"])

    def replace_event_trigger(
        self, workspace_id: str, trigger_id: str, definition: Mapping[str, object]
    ) -> Mapping[str, object]:
        if not workspace_id.strip() or not trigger_id.strip():
            raise ValueError("workspace_id and trigger_id must be non-empty")
        if not isinstance(definition, Mapping):
            raise ValueError("event trigger definition must be an object")
        result = self._transport.request(
            "PUT",
            f"/v1/workspaces/{quote(workspace_id, safe='')}/event-triggers/"
            f"{quote(trigger_id, safe='')}",
            payload=dict(definition),
        )
        if not isinstance(result, dict):
            raise ProtocolError("event trigger response must be an object")
        return result

    def ingest_scheduler_event(
        self,
        workspace_id: str,
        event_id: str,
        event_type: str,
        payload_digest: str,
        occurred_at: str,
        *,
        source_ref: str | None = None,
        subject_ref: str | None = None,
        received_at: str | None = None,
    ) -> Mapping[str, object]:
        """Ingest one idempotent scheduler event into the durable inbox."""
        if not all(
            isinstance(value, str) and value.strip()
            for value in (workspace_id, event_id, event_type, payload_digest, occurred_at)
        ):
            raise ValueError("event identity, type, digest, and occurred_at are required")
        payload: dict[str, object] = {
            "event_id": event_id,
            "event_type": event_type,
            "payload_digest": payload_digest,
            "occurred_at": occurred_at,
        }
        if source_ref is not None:
            payload["source_ref"] = source_ref
        if subject_ref is not None:
            payload["subject_ref"] = subject_ref
        if received_at is not None:
            payload["received_at"] = received_at
        result = self._transport.request(
            "POST",
            f"/v1/workspaces/{quote(workspace_id, safe='')}/events",
            payload=payload,
        )
        if not isinstance(result, dict):
            raise ProtocolError("event ingestion response must be an object")
        return result

    def list_pending_event_deliveries(
        self, workspace_id: str, *, limit: int = 100
    ) -> tuple[Mapping[str, object], ...]:
        """List bounded pending scheduler event deliveries."""
        if not workspace_id.strip():
            raise ValueError("workspace_id must be non-empty")
        if isinstance(limit, bool) or limit < 1 or limit > 100:
            raise ValueError("limit must be between 1 and 100")
        result = self._transport.request(
            "GET",
            f"/v1/workspaces/{quote(workspace_id, safe='')}/event-deliveries",
            query={"limit": str(limit)},
        )
        if not isinstance(result, dict) or not isinstance(result.get("items"), list):
            raise ProtocolError("event delivery response must contain an items array")
        if not all(isinstance(item, dict) for item in result["items"]):
            raise ProtocolError("event delivery items must be objects")
        return tuple(result["items"])

    def get_workflow_run(self, workspace_id: str, run_id: str) -> Mapping[str, object]:
        """Read one durable workflow run together with task state."""
        if not workspace_id.strip() or not run_id.strip():
            raise ValueError("workspace_id and run_id must be non-empty")
        result = self._transport.request(
            "GET",
            f"/v1/workspaces/{quote(workspace_id, safe='')}/workflow-runs/{quote(run_id, safe='')}",
        )
        if not isinstance(result, dict):
            raise ProtocolError("workflow run response must be an object")
        if not isinstance(result.get("tasks"), list):
            raise ProtocolError("workflow run response must contain tasks")
        return result

    def cancel_workflow_run(self, workspace_id: str, run_id: str) -> Mapping[str, object]:
        """Request cancellation of one workflow run."""
        if not workspace_id.strip() or not run_id.strip():
            raise ValueError("workspace_id and run_id must be non-empty")
        result = self._transport.request(
            "POST",
            f"/v1/workspaces/{quote(workspace_id, safe='')}/workflow-runs/"
            f"{quote(run_id, safe='')}/cancel",
            payload={},
        )
        if not isinstance(result, dict):
            raise ProtocolError("workflow cancellation response must be an object")
        return result

    def create_workflow_run(
        self,
        workspace_id: str,
        workflow_id: str,
        trigger: Mapping[str, object],
        *,
        idempotency_key: str,
    ) -> Mapping[str, object]:
        """Create one idempotent durable workflow run."""
        if not workspace_id.strip() or not workflow_id.strip() or not idempotency_key.strip():
            raise ValueError("workspace_id, workflow_id, and idempotency_key are required")
        if not isinstance(trigger, Mapping):
            raise ValueError("trigger must be an object")
        result = self._transport.request(
            "POST",
            f"/v1/workspaces/{quote(workspace_id, safe='')}/workflows/"
            f"{quote(workflow_id, safe='')}/runs",
            payload={"trigger": dict(trigger), "idempotency_key": idempotency_key},
        )
        if not isinstance(result, dict):
            raise ProtocolError("workflow run creation response must be an object")
        return result

    def create_backfill(
        self,
        workspace_id: str,
        backfill_id: str,
        schedule_id: str,
        start_at: str,
        end_at: str,
    ) -> Mapping[str, object]:
        """Create a bounded scheduler backfill operation."""
        values = (workspace_id, backfill_id, schedule_id, start_at, end_at)
        if not all(isinstance(value, str) and value.strip() for value in values):
            raise ValueError("backfill identifiers and timestamps must be non-empty")
        payload = self._transport.request(
            "POST",
            f"/v1/workspaces/{quote(workspace_id, safe='')}/backfills",
            payload={
                "id": backfill_id,
                "schedule_id": schedule_id,
                "start_at": start_at,
                "end_at": end_at,
            },
        )
        if not isinstance(payload, dict):
            raise ProtocolError("backfill response must be an object")
        return payload

    def preview_backfill(
        self,
        workspace_id: str,
        schedule_id: str,
        start_at: str,
        end_at: str,
        *,
        max_runs: int = 1000,
    ) -> tuple[str, ...]:
        """Preview bounded backfill fire times without submitting a request."""
        if not all(
            isinstance(value, str) and value.strip()
            for value in (workspace_id, schedule_id, start_at, end_at)
        ):
            raise ValueError("backfill preview identifiers and timestamps are required")
        if isinstance(max_runs, bool) or max_runs < 1 or max_runs > 10000:
            raise ValueError("max_runs must be between 1 and 10000")
        result = self._transport.request(
            "POST",
            f"/v1/workspaces/{quote(workspace_id, safe='')}/backfills/preview",
            payload={
                "schedule_id": schedule_id,
                "start_at": start_at,
                "end_at": end_at,
                "max_runs": max_runs,
            },
        )
        if not isinstance(result, dict) or not isinstance(result.get("items"), list):
            raise ProtocolError("backfill preview response must contain an items array")
        if not all(isinstance(item, str) for item in result["items"]):
            raise ProtocolError("backfill preview items must be strings")
        return tuple(result["items"])

    def get_backfill(self, workspace_id: str, backfill_id: str) -> Mapping[str, object]:
        """Read a scheduler backfill operation."""
        if not workspace_id.strip() or not backfill_id.strip():
            raise ValueError("workspace_id and backfill_id must be non-empty")
        payload = self._transport.request(
            "GET",
            f"/v1/workspaces/{quote(workspace_id, safe='')}/backfills/"
            f"{quote(backfill_id, safe='')}",
        )
        if not isinstance(payload, dict):
            raise ProtocolError("backfill response must be an object")
        return payload

    def cancel_backfill(self, workspace_id: str, backfill_id: str) -> Mapping[str, object]:
        """Cancel a scheduler backfill operation."""
        if not workspace_id.strip() or not backfill_id.strip():
            raise ValueError("workspace_id and backfill_id must be non-empty")
        payload = self._transport.request(
            "POST",
            f"/v1/workspaces/{quote(workspace_id, safe='')}/backfills/"
            f"{quote(backfill_id, safe='')}/cancel",
            payload={},
        )
        if not isinstance(payload, dict):
            raise ProtocolError("backfill response must be an object")
        return payload

    def get_pipeline_revision(
        self, workspace_id: str, project_id: str, pipeline_id: str, revision: int
    ) -> Mapping[str, object]:
        """Read one immutable Data Engineering pipeline revision."""
        if not workspace_id.strip() or not project_id.strip() or not pipeline_id.strip():
            raise ValueError("workspace_id, project_id, and pipeline_id must be non-empty")
        if isinstance(revision, bool) or revision < 1:
            raise ValueError("revision must be positive")
        payload = self._transport.request(
            "GET",
            f"/v1/workspaces/{quote(workspace_id, safe='')}/projects/{quote(project_id, safe='')}"
            f"/pipelines/{quote(pipeline_id, safe='')}/revisions/{revision}",
        )
        if not isinstance(payload, dict):
            raise ProtocolError("pipeline revision response must be an object")
        return payload

    def compare_pipeline_revisions(
        self,
        workspace_id: str,
        project_id: str,
        pipeline_id: str,
        left_revision: int,
        right_revision: int,
    ) -> Mapping[str, object]:
        if not workspace_id.strip() or not project_id.strip() or not pipeline_id.strip():
            raise ValueError("workspace_id, project_id, and pipeline_id must be non-empty")
        if left_revision < 1 or right_revision < 1:
            raise ValueError("revisions must be positive")
        payload = self._transport.request(
            "GET",
            f"/v1/workspaces/{quote(workspace_id, safe='')}/projects/{quote(project_id, safe='')}"
            f"/pipelines/{quote(pipeline_id, safe='')}/revisions/compare",
            query={
                "left_revision": str(left_revision),
                "right_revision": str(right_revision),
            },
        )
        if not isinstance(payload, dict):
            raise ProtocolError("pipeline comparison response must be an object")
        return payload

    def archive_pipeline(self, workspace_id: str, project_id: str, pipeline_id: str) -> bool:
        """Archive a Data Engineering pipeline without deleting its revisions."""
        if not workspace_id.strip() or not project_id.strip() or not pipeline_id.strip():
            raise ValueError("workspace_id, project_id, and pipeline_id must be non-empty")
        payload = self._transport.request(
            "POST",
            f"/v1/workspaces/{quote(workspace_id, safe='')}/projects/{quote(project_id, safe='')}"
            f"/pipelines/{quote(pipeline_id, safe='')}/archive",
        )
        return isinstance(payload, dict) and payload.get("archived") is True

    def import_pipeline_revision(
        self,
        workspace_id: str,
        project_id: str,
        pipeline_id: str,
        *,
        project_name: str,
        project_yaml: bytes,
        pipeline_documents: Mapping[str, bytes],
        expected_revision: int | None = None,
    ) -> Mapping[str, object]:
        """Import one SDP pipeline revision through the Data Engineering port."""
        if (
            not workspace_id.strip()
            or not project_id.strip()
            or not pipeline_id.strip()
            or not project_name.strip()
        ):
            raise ValueError("workspace, project, pipeline, and project_name must be non-empty")
        if (
            not isinstance(project_yaml, bytes)
            or not project_yaml
            or not all(
                isinstance(name, str) and name.strip() and isinstance(content, bytes) and content
                for name, content in pipeline_documents.items()
            )
        ):
            raise ValueError("project_yaml and pipeline documents must contain non-empty bytes")
        if expected_revision is not None and (
            isinstance(expected_revision, bool) or expected_revision < 0
        ):
            raise ValueError("expected_revision must be a non-negative integer")
        body = {
            "project_name": project_name,
            "project_yaml_base64": base64.b64encode(project_yaml).decode("ascii"),
            "pipeline_documents": [
                {"name": name, "content_base64": base64.b64encode(content).decode("ascii")}
                for name, content in pipeline_documents.items()
            ],
        }
        if expected_revision is not None:
            body["expected_revision"] = expected_revision
        payload = self._transport.request(
            "POST",
            f"/v1/workspaces/{quote(workspace_id, safe='')}/projects/"
            f"{quote(project_id, safe='')}/pipelines/{quote(pipeline_id, safe='')}/revisions",
            payload=body,
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("revision"), int):
            raise ProtocolError("pipeline revision import response has invalid shape")
        return payload

    def list_environments(self, workspace_id: str) -> tuple[Environment, ...]:
        if not workspace_id.strip():
            raise ValueError("workspace_id must be non-empty")
        payload = self._transport.request(
            "GET", f"/v1/workspaces/{quote(workspace_id, safe='')}/environments"
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            raise ProtocolError("environments response must contain an items array")
        return tuple(_parse_environment(item) for item in payload["items"])

    def get_environment(self, workspace_id: str, environment_id: str) -> Environment:
        if not workspace_id.strip() or not environment_id.strip():
            raise ValueError("workspace_id and environment_id must be non-empty")
        return _parse_environment(
            self._transport.request(
                "GET",
                f"/v1/workspaces/{quote(workspace_id, safe='')}/environments/"
                f"{quote(environment_id, safe='')}",
            )
        )

    def create_environment(
        self, workspace_id: str, definition: Mapping[str, object]
    ) -> Environment:
        if not workspace_id.strip():
            raise ValueError("workspace_id must be non-empty")
        return _parse_environment(
            self._transport.request(
                "POST",
                f"/v1/workspaces/{quote(workspace_id, safe='')}/environments",
                payload=dict(definition),
            )
        )

    def update_environment(
        self, workspace_id: str, environment_id: str, definition: Mapping[str, object]
    ) -> Environment:
        if not workspace_id.strip() or not environment_id.strip():
            raise ValueError("workspace_id and environment_id must be non-empty")
        return _parse_environment(
            self._transport.request(
                "PUT",
                f"/v1/workspaces/{quote(workspace_id, safe='')}/environments/"
                f"{quote(environment_id, safe='')}",
                payload=dict(definition),
            )
        )

    def disable_environment(self, workspace_id: str, environment_id: str) -> Environment:
        if not workspace_id.strip() or not environment_id.strip():
            raise ValueError("workspace_id and environment_id must be non-empty")
        return _parse_environment(
            self._transport.request(
                "POST",
                f"/v1/workspaces/{quote(workspace_id, safe='')}/environments/"
                f"{quote(environment_id, safe='')}/disable",
            )
        )

    def diff_environment(
        self, workspace_id: str, environment_id: str, definition: Mapping[str, object]
    ) -> Mapping[str, object]:
        if not workspace_id.strip() or not environment_id.strip():
            raise ValueError("workspace_id and environment_id must be non-empty")
        payload = self._transport.request(
            "POST",
            f"/v1/workspaces/{quote(workspace_id, safe='')}/environments/"
            f"{quote(environment_id, safe='')}/diff",
            payload=dict(definition),
        )
        if not isinstance(payload, dict):
            raise ProtocolError("environment diff response must be an object")
        return payload

    def get_environment_bindings(
        self, workspace_id: str, project_id: str, environment_id: str
    ) -> ProjectEnvironmentBindings:
        if not workspace_id.strip() or not project_id.strip() or not environment_id.strip():
            raise ValueError("workspace_id, project_id and environment_id must be non-empty")
        return _parse_bindings(
            self._transport.request(
                "GET",
                f"/v1/workspaces/{quote(workspace_id, safe='')}/projects/"
                f"{quote(project_id, safe='')}/environments/"
                f"{quote(environment_id, safe='')}/bindings",
            )
        )

    def put_environment_bindings(
        self, workspace_id: str, bindings: ProjectEnvironmentBindings
    ) -> ProjectEnvironmentBindings:
        if not workspace_id.strip():
            raise ValueError("workspace_id must be non-empty")
        return _parse_bindings(
            self._transport.request(
                "PUT",
                f"/v1/workspaces/{quote(workspace_id, safe='')}/projects/"
                f"{quote(bindings.project_id, safe='')}/environments/"
                f"{quote(bindings.environment_id, safe='')}/bindings",
                payload={
                    "project_id": bindings.project_id,
                    "environment_id": bindings.environment_id,
                    "bindings": [
                        {
                            "kind": item.kind,
                            "source_ref": item.source_ref,
                            "target_ref": item.target_ref,
                        }
                        for item in bindings.bindings
                    ],
                },
            )
        )

    def list_security_principals(self) -> tuple[Principal, ...]:
        payload = self._transport.request("GET", "/v1/admin/security/principals")
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            raise ProtocolError("principals response must contain an items array")
        return tuple(_parse_principal(item) for item in payload["items"])

    def get_security_principal(self, principal_id: str) -> Principal:
        if not principal_id.strip():
            raise ValueError("principal_id must be non-empty")
        return _parse_principal(
            self._transport.request(
                "GET", f"/v1/admin/security/principals/{quote(principal_id, safe='')}"
            )
        )

    def put_security_principal(
        self, principal_id: str, definition: Mapping[str, object]
    ) -> Principal:
        if not principal_id.strip():
            raise ValueError("principal_id must be non-empty")
        return _parse_principal(
            self._transport.request(
                "PUT",
                f"/v1/admin/security/principals/{quote(principal_id, safe='')}",
                payload=dict(definition),
            )
        )

    def list_security_groups(self) -> tuple[Group, ...]:
        payload = self._transport.request("GET", "/v1/admin/security/groups")
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            raise ProtocolError("groups response must contain an items array")
        return tuple(_parse_group(item) for item in payload["items"])

    def get_security_group(self, group_id: str) -> Group:
        if not group_id.strip():
            raise ValueError("group_id must be non-empty")
        return _parse_group(
            self._transport.request("GET", f"/v1/admin/security/groups/{quote(group_id, safe='')}")
        )

    def put_security_group(self, group_id: str, name: str) -> Group:
        if not group_id.strip() or not name.strip():
            raise ValueError("group_id and name must be non-empty")
        return _parse_group(
            self._transport.request(
                "PUT",
                f"/v1/admin/security/groups/{quote(group_id, safe='')}",
                payload={"name": name},
            )
        )

    def list_security_group_members(self, group_id: str) -> tuple[Principal, ...]:
        if not group_id.strip():
            raise ValueError("group_id must be non-empty")
        payload = self._transport.request(
            "GET", f"/v1/admin/security/groups/{quote(group_id, safe='')}/members"
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            raise ProtocolError("group members response must contain an items array")
        return tuple(_parse_principal(item) for item in payload["items"])

    def add_security_group_member(self, group_id: str, principal_id: str) -> bool:
        if not group_id.strip() or not principal_id.strip():
            raise ValueError("group_id and principal_id must be non-empty")
        payload = self._transport.request(
            "PUT",
            f"/v1/admin/security/groups/{quote(group_id, safe='')}/members/"
            f"{quote(principal_id, safe='')}",
        )
        return isinstance(payload, dict) and payload.get("member") is True

    def remove_security_group_member(self, group_id: str, principal_id: str) -> bool:
        if not group_id.strip() or not principal_id.strip():
            raise ValueError("group_id and principal_id must be non-empty")
        payload = self._transport.request(
            "DELETE",
            f"/v1/admin/security/groups/{quote(group_id, safe='')}/members/"
            f"{quote(principal_id, safe='')}",
        )
        return isinstance(payload, dict) and payload.get("member") is False

    def list_role_bindings(self) -> tuple[RoleBinding, ...]:
        payload = self._transport.request("GET", "/v1/admin/security/role-bindings")
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            raise ProtocolError("role bindings response must contain an items array")
        return tuple(_parse_role_binding(item) for item in payload["items"])

    def put_role_binding(self, subject_kind: str, subject_id: str, role: str) -> RoleBinding:
        if not all(value.strip() for value in (subject_kind, subject_id, role)):
            raise ValueError("subject_kind, subject_id and role must be non-empty")
        return _parse_role_binding(
            self._transport.request(
                "PUT",
                f"/v1/admin/security/role-bindings/{quote(subject_kind, safe='')}/"
                f"{quote(subject_id, safe='')}/{quote(role, safe='')}",
            )
        )

    def delete_role_binding(self, subject_kind: str, subject_id: str, role: str) -> bool:
        if not all(value.strip() for value in (subject_kind, subject_id, role)):
            raise ValueError("subject_kind, subject_id and role must be non-empty")
        payload = self._transport.request(
            "DELETE",
            f"/v1/admin/security/role-bindings/{quote(subject_kind, safe='')}/"
            f"{quote(subject_id, safe='')}/{quote(role, safe='')}",
        )
        return isinstance(payload, dict) and payload.get("removed") is True

    def submit(
        self,
        *,
        project: str,
        target: str,
        parameters: Mapping[str, object] | None = None,
        idempotency_key: str | None = None,
    ) -> JobHandle:
        if not project.strip():
            raise ValueError("project must be non-empty")
        if not target.strip():
            raise ValueError("target must be non-empty")
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
        payload = self._transport.request(
            "POST",
            "/v1/jobs",
            payload={"project": project, "target": target, "parameters": dict(parameters or {})},
            headers=headers,
        )
        job = _parse_job(payload)
        return JobHandle(self, job.id)

    def execute_sql(
        self,
        *,
        project: str,
        sql: str,
        parameters: tuple[object, ...] = (),
        max_rows: int = 10_000,
        profile: str = "local",
        translation_policy: str = "native_only",
    ) -> SqlResult:
        if not project.strip():
            raise ValueError("project must be non-empty")
        if not sql or sql != sql.strip():
            raise ValueError("sql must be non-empty and trimmed")
        if not 1 <= max_rows <= 10_000:
            raise ValueError("max_rows must be between 1 and 10000")
        if profile not in {"local", "queryflux"}:
            raise ValueError("profile is unsupported")
        if translation_policy not in {"native_only", "best_effort", "strict"}:
            raise ValueError("translation_policy is unsupported")
        request_payload: dict[str, object] = {
            "project": project,
            "sql": sql,
            "parameters": list(parameters),
            "max_rows": max_rows,
        }
        if profile != "local":
            request_payload["profile"] = profile
        if translation_policy != "native_only":
            request_payload["translation_policy"] = translation_policy
        payload = self._transport.request(
            "POST",
            "/v1/sql",
            payload=request_payload,
        )
        return _parse_sql_result(payload)

    def list_catalog_assets(
        self, workspace_id: str, *, query: str | None = None, limit: int = 100
    ) -> tuple[CatalogAsset, ...]:
        if not workspace_id.strip():
            raise ValueError("workspace_id must be non-empty")
        if query is not None and not query.strip():
            raise ValueError("query must be non-empty when supplied")
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        params = {"limit": str(limit)}
        if query is not None:
            params["q"] = query
        payload = self._transport.request(
            "GET", f"/v1/workspaces/{quote(workspace_id, safe='')}/catalog/assets", query=params
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            raise ProtocolError("catalog assets response must contain an items array")
        result: list[CatalogAsset] = []
        for item in payload["items"]:
            if not isinstance(item, dict) or not all(
                isinstance(item.get(field), str) and item[field] for field in ("id", "kind", "name")
            ):
                raise ProtocolError("catalog asset has invalid identity fields")
            tags = item.get("tags", [])
            classifications = item.get("classifications", [])
            if not all(isinstance(value, str) for value in (*tags, *classifications)):
                raise ProtocolError("catalog asset metadata must contain strings")
            result.append(
                CatalogAsset(
                    item["id"], item["kind"], item["name"], tuple(tags), tuple(classifications)
                )
            )
        return tuple(result)

    def list_catalog_lineage(
        self, workspace_id: str, asset_id: str, version: str, *, direction: str = "upstream"
    ) -> tuple[CatalogLineageEdge, ...]:
        if not workspace_id.strip() or not asset_id.strip() or not version.strip():
            raise ValueError("workspace_id, asset_id and version must be non-empty")
        if direction not in {"upstream", "downstream"}:
            raise ValueError("direction must be upstream or downstream")
        payload = self._transport.request(
            "GET",
            f"/v1/workspaces/{quote(workspace_id, safe='')}/catalog/lineage/"
            f"{quote(asset_id, safe='')}/{quote(version, safe='')}",
            query={"direction": direction},
        )
        items = payload.get("items") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            raise ProtocolError("lineage response must contain an items array")
        result: list[CatalogLineageEdge] = []
        for item in items:
            if (
                not isinstance(item, dict)
                or not isinstance(item.get("source"), dict)
                or not isinstance(item.get("target"), dict)
            ):
                raise ProtocolError("lineage edge has invalid endpoints")
            mappings = item.get("column_mappings", [])
            if not isinstance(mappings, list) or not all(
                isinstance(value, dict) for value in mappings
            ):
                raise ProtocolError("lineage edge mappings must be objects")
            result.append(
                CatalogLineageEdge(
                    item["source"],
                    item["target"],
                    str(item.get("operation", "")),
                    str(item.get("mode", "")),
                    item.get("execution_ref"),
                    tuple(mappings),
                )
            )
        return tuple(result)

    def list_catalog_revisions(
        self, workspace_id: str, asset_id: str
    ) -> tuple[Mapping[str, object], ...]:
        if not workspace_id.strip() or not asset_id.strip():
            raise ValueError("workspace_id and asset_id must be non-empty")
        payload = self._transport.request(
            "GET",
            f"/v1/workspaces/{quote(workspace_id, safe='')}/catalog/assets/"
            f"{quote(asset_id, safe='')}/revisions",
        )
        return self._catalog_items(payload, "catalog revisions")

    def get_catalog_revision(
        self, workspace_id: str, asset_id: str, version: str
    ) -> Mapping[str, object]:
        if not workspace_id.strip() or not asset_id.strip() or not version.strip():
            raise ValueError("workspace_id, asset_id and version must be non-empty")
        payload = self._transport.request(
            "GET",
            f"/v1/workspaces/{quote(workspace_id, safe='')}/catalog/assets/"
            f"{quote(asset_id, safe='')}/revisions/{quote(version, safe='')}",
        )
        if not isinstance(payload, dict):
            raise ProtocolError("catalog revision response must be an object")
        return payload

    @staticmethod
    def _catalog_items(payload: object, label: str) -> tuple[Mapping[str, object], ...]:
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            raise ProtocolError(f"{label} response must contain an items array")
        if not all(isinstance(item, dict) for item in payload["items"]):
            raise ProtocolError(f"{label} items must be objects")
        return tuple(payload["items"])

    def list_glossary_terms(
        self, workspace_id: str, *, query: str | None = None, limit: int = 100
    ) -> tuple[GlossaryTerm, ...]:
        if not workspace_id.strip():
            raise ValueError("workspace_id must be non-empty")
        if query is not None and not query.strip():
            raise ValueError("query must be non-empty when supplied")
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        params = {"limit": str(limit)}
        if query is not None:
            params["q"] = query
        payload = self._transport.request(
            "GET",
            f"/v1/workspaces/{quote(workspace_id, safe='')}/glossary/terms",
            query=params,
        )
        items = payload.get("items") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            raise ProtocolError("glossary response must contain an items array")
        return tuple(self._parse_glossary_term(item) for item in items)

    def get_glossary_term(self, workspace_id: str, term_id: str, version: str) -> GlossaryTerm:
        if not workspace_id.strip() or not term_id.strip() or not version.strip():
            raise ValueError("workspace_id, term_id and version must be non-empty")
        payload = self._transport.request(
            "GET",
            f"/v1/workspaces/{quote(workspace_id, safe='')}/glossary/terms/"
            f"{quote(term_id, safe='')}/{quote(version, safe='')}",
        )
        return self._parse_glossary_term(payload)

    def put_glossary_term(self, workspace_id: str, term: GlossaryTerm) -> GlossaryTerm:
        if not workspace_id.strip():
            raise ValueError("workspace_id must be non-empty")
        payload = self._transport.request(
            "POST",
            f"/v1/workspaces/{quote(workspace_id, safe='')}/glossary/terms",
            payload={
                "id": term.id,
                "version": term.version,
                "name": term.name,
                "definition": term.definition,
                "owner": term.owner,
                "references": list(term.references),
            },
        )
        return self._parse_glossary_term(payload)

    @staticmethod
    def _parse_glossary_term(payload: object) -> GlossaryTerm:
        if not isinstance(payload, dict) or not all(
            isinstance(payload.get(key), str) and payload[key]
            for key in ("id", "version", "name", "definition", "owner")
        ):
            raise ProtocolError("glossary term has invalid identity or text fields")
        references = payload.get("references", [])
        if not isinstance(references, list) or not all(
            isinstance(value, str) for value in references
        ):
            raise ProtocolError("glossary term references must be strings")
        return GlossaryTerm(
            payload["id"],
            payload["version"],
            payload["name"],
            payload["definition"],
            payload["owner"],
            tuple(references),
        )

    def put_catalog_ownership(
        self, workspace_id: str, asset_id: str, metadata: OwnershipMetadata
    ) -> OwnershipMetadata:
        if not workspace_id.strip() or not asset_id.strip():
            raise ValueError("workspace_id and asset_id must be non-empty")
        payload = self._transport.request(
            "POST",
            f"/v1/workspaces/{quote(workspace_id, safe='')}/catalog/assets/"
            f"{quote(asset_id, safe='')}/ownership",
            payload={
                "version": metadata.version,
                "owner_ref": metadata.owner_ref,
                "steward_refs": list(metadata.steward_refs),
                "domain": metadata.domain,
                "lifecycle": metadata.lifecycle,
            },
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("version"), int):
            raise ProtocolError("ownership response has invalid version")
        stewards = payload.get("steward_refs", [])
        if not isinstance(payload.get("owner_ref"), str) or not isinstance(stewards, list):
            raise ProtocolError("ownership response has invalid fields")
        domain = payload.get("domain")
        lifecycle = payload.get("lifecycle")
        if domain is not None and not isinstance(domain, str) or not isinstance(lifecycle, str):
            raise ProtocolError("ownership response has invalid lifecycle fields")
        return OwnershipMetadata(
            payload["version"], payload["owner_ref"], tuple(stewards), domain, lifecycle
        )

    def put_catalog_sensitivity(
        self, workspace_id: str, asset_id: str, metadata: SensitivityMetadata
    ) -> SensitivityMetadata:
        if not workspace_id.strip() or not asset_id.strip():
            raise ValueError("workspace_id and asset_id must be non-empty")
        payload = self._transport.request(
            "POST",
            f"/v1/workspaces/{quote(workspace_id, safe='')}/catalog/assets/"
            f"{quote(asset_id, safe='')}/sensitivity",
            payload={
                "version": metadata.version,
                "explicit": list(metadata.explicit),
                "inherited": list(metadata.inherited),
                "inherited_from": list(metadata.inherited_from),
                "effective": sorted(set(metadata.explicit) | set(metadata.inherited)),
            },
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("version"), int):
            raise ProtocolError("sensitivity response has invalid version")
        fields = [payload.get(name) for name in ("explicit", "inherited", "inherited_from")]
        if not all(
            isinstance(value, list) and all(isinstance(item, str) for item in value)
            for value in fields
        ):
            raise ProtocolError("sensitivity response has invalid label fields")
        return SensitivityMetadata(
            payload["version"], tuple(fields[0]), tuple(fields[1]), tuple(fields[2])
        )

    def get_quality_contract(
        self, workspace_id: str, asset_id: str, version: str
    ) -> Mapping[str, object]:
        return self._quality_get(
            workspace_id, f"contracts/{quote(asset_id, safe='')}/{quote(version, safe='')}"
        )

    def run_quality(self, workspace_id: str, request: Mapping[str, object]) -> Mapping[str, object]:
        if not workspace_id.strip() or not isinstance(request, Mapping):
            raise ValueError("workspace_id and quality request are required")
        payload = self._transport.request(
            "POST",
            f"/v1/workspaces/{quote(workspace_id, safe='')}/quality/runs",
            payload=dict(request),
        )
        return self._quality_object(payload, "quality run")

    def list_quality_runs(
        self, workspace_id: str, asset_id: str, version: str
    ) -> tuple[Mapping[str, object], ...]:
        return self._quality_items(
            workspace_id, f"runs/{quote(asset_id, safe='')}/{quote(version, safe='')}"
        )

    def get_quality_state(
        self, workspace_id: str, asset_id: str, version: str
    ) -> Mapping[str, object]:
        return self._quality_get(
            workspace_id, f"state/{quote(asset_id, safe='')}/{quote(version, safe='')}"
        )

    def _quality_get(self, workspace_id: str, suffix: str) -> Mapping[str, object]:
        if not workspace_id.strip():
            raise ValueError("workspace_id must be non-empty")
        return self._quality_object(
            self._transport.request(
                "GET", f"/v1/workspaces/{quote(workspace_id, safe='')}/quality/{suffix}"
            ),
            "quality response",
        )

    def _quality_items(self, workspace_id: str, suffix: str) -> tuple[Mapping[str, object], ...]:
        if not workspace_id.strip():
            raise ValueError("workspace_id must be non-empty")
        payload = self._transport.request(
            "GET", f"/v1/workspaces/{quote(workspace_id, safe='')}/quality/{suffix}"
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            raise ProtocolError("quality history response must contain an items array")
        if not all(isinstance(item, dict) for item in payload["items"]):
            raise ProtocolError("quality history items must be objects")
        return tuple(payload["items"])

    @staticmethod
    def _quality_object(payload: object, label: str) -> Mapping[str, object]:
        if not isinstance(payload, dict):
            raise ProtocolError(f"{label} response must be an object")
        return payload

    def streaming_health(self, workspace_id: str, stream_id: str) -> StreamingHealth:
        if not workspace_id.strip() or not stream_id.strip():
            raise ValueError("workspace_id and stream_id must be non-empty")
        payload = self._transport.request(
            "GET",
            "/v1/workspaces/"
            f"{quote(workspace_id, safe='')}/streams/{quote(stream_id, safe='')}/health",
        )
        if not isinstance(payload, dict):
            raise ProtocolError("streaming health response must be an object")
        required = ("stream_id", "checkpoint_digest", "partitions", "lag", "total_lag", "healthy")
        if not all(key in payload for key in required):
            raise ProtocolError("streaming health response is missing fields")
        if (
            payload["stream_id"] != stream_id
            or not isinstance(payload["checkpoint_digest"], str)
            or not payload["checkpoint_digest"].strip()
        ):
            raise ProtocolError("streaming health identity is invalid")
        lag = payload["lag"]
        if not isinstance(lag, dict) or not all(
            isinstance(key, str)
            and isinstance(value, int)
            and not isinstance(value, bool)
            and value >= 0
            for key, value in lag.items()
        ):
            raise ProtocolError("streaming health lag must be a non-negative integer map")
        if (
            not isinstance(payload["partitions"], int)
            or isinstance(payload["partitions"], bool)
            or payload["partitions"] < 0
        ):
            raise ProtocolError("streaming health partitions must be non-negative")
        if (
            not isinstance(payload["total_lag"], int)
            or isinstance(payload["total_lag"], bool)
            or payload["total_lag"] < 0
        ):
            raise ProtocolError("streaming health total_lag must be non-negative")
        if not isinstance(payload["healthy"], bool):
            raise ProtocolError("streaming health healthy must be boolean")
        return StreamingHealth(
            stream_id,
            payload["checkpoint_digest"],
            payload["partitions"],
            dict(lag),
            payload["total_lag"],
            payload["healthy"],
        )

    def list_finops_usage(
        self, workspace_id: str, *, period_start: str, period_end: str
    ) -> tuple[Mapping[str, object], ...]:
        return self._list_finops(workspace_id, "usage", period_start, period_end)

    def list_finops_costs(
        self, workspace_id: str, *, period_start: str, period_end: str
    ) -> tuple[Mapping[str, object], ...]:
        return self._list_finops(workspace_id, "costs", period_start, period_end)

    def list_finops_budgets(self, workspace_id: str) -> tuple[Mapping[str, object], ...]:
        if not workspace_id.strip():
            raise ValueError("workspace_id must be non-empty")
        return self._finops_items(
            self._transport.request(
                "GET",
                f"/v1/workspaces/{quote(workspace_id, safe='')}/finops/budgets",
            )
        )

    def _list_finops(
        self, workspace_id: str, kind: str, period_start: str, period_end: str
    ) -> tuple[Mapping[str, object], ...]:
        if not workspace_id.strip() or not period_start.strip() or not period_end.strip():
            raise ValueError("workspace_id, period_start and period_end must be non-empty")
        return self._finops_items(
            self._transport.request(
                "GET",
                f"/v1/workspaces/{quote(workspace_id, safe='')}/finops/{kind}",
                query={"period_start": period_start, "period_end": period_end},
            )
        )

    @staticmethod
    def _finops_items(payload: object) -> tuple[Mapping[str, object], ...]:
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            raise ProtocolError("finops response must contain an items array")
        if not all(isinstance(item, dict) for item in payload["items"]):
            raise ProtocolError("finops items must be objects")
        return tuple(payload["items"])

    def list_alert_rules(self, workspace_id: str) -> tuple[dict[str, object], ...]:
        if not workspace_id.strip():
            raise ValueError("workspace_id must be non-empty")
        payload = self._transport.request(
            "GET", f"/v1/workspaces/{quote(workspace_id, safe='')}/alerts/rules"
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            raise ProtocolError("alert rules response must contain an items array")
        if not all(isinstance(item, dict) for item in payload["items"]):
            raise ProtocolError("alert rule items must be objects")
        return tuple(payload["items"])

    def list_ml_feature_definitions(self, workspace_id: str) -> tuple[Mapping[str, object], ...]:
        if not workspace_id.strip():
            raise ValueError("workspace_id must be non-empty")
        payload = self._transport.request(
            "GET", "/v1/ml-studio/features", query={"workspace_id": workspace_id}
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            raise ProtocolError("feature definitions response must contain an items array")
        if not all(isinstance(item, dict) for item in payload["items"]):
            raise ProtocolError("feature definition items must be objects")
        return tuple(payload["items"])

    def publish_ml_feature_definition(
        self, workspace_id: str, definition: Mapping[str, object]
    ) -> Mapping[str, object]:
        if not workspace_id.strip():
            raise ValueError("workspace_id must be non-empty")
        payload = self._transport.request(
            "POST",
            "/v1/ml-studio/features",
            query={"workspace_id": workspace_id},
            payload=dict(definition),
        )
        if not isinstance(payload, dict):
            raise ProtocolError("feature definition response must be an object")
        return payload

    def get_ml_feature_definition(
        self, workspace_id: str, feature_id: str, version: int
    ) -> Mapping[str, object]:
        if not workspace_id.strip() or not feature_id.strip():
            raise ValueError("workspace_id and feature_id must be non-empty")
        if isinstance(version, bool) or version < 1:
            raise ValueError("version must be a positive integer")
        payload = self._transport.request(
            "GET",
            f"/v1/ml-studio/features/{quote(feature_id, safe='')}/{version}",
            query={"workspace_id": workspace_id},
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            raise ProtocolError("feature definition response must contain an items array")
        if len(payload["items"]) != 1 or not isinstance(payload["items"][0], dict):
            raise ProtocolError("feature definition response must contain one object")
        return payload["items"][0]

    def list_alert_instances(
        self, workspace_id: str, *, limit: int = 100
    ) -> tuple[dict[str, object], ...]:
        if not workspace_id.strip() or not 1 <= limit <= 1000:
            raise ValueError("workspace_id must be non-empty and limit must be between 1 and 1000")
        payload = self._transport.request(
            "GET",
            f"/v1/workspaces/{quote(workspace_id, safe='')}/alerts/instances",
            query={"limit": str(limit)},
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            raise ProtocolError("alert instances response must contain an items array")
        if not all(isinstance(item, dict) for item in payload["items"]):
            raise ProtocolError("alert instance items must be objects")
        return tuple(payload["items"])

    def evaluate_alert(self, workspace_id: str, rule_id: str) -> Mapping[str, object]:
        if not workspace_id.strip() or not rule_id.strip():
            raise ValueError("workspace_id and rule_id must be non-empty")
        payload = self._transport.request(
            "POST",
            f"/v1/workspaces/{quote(workspace_id, safe='')}/alerts/evaluate",
            payload={"rule_id": rule_id},
        )
        if not isinstance(payload, dict) or payload.get("rule_id") != rule_id:
            raise ProtocolError("alert evaluation response must contain matching rule_id")
        return payload

    def acknowledge_alert(
        self, workspace_id: str, rule_id: str, fingerprint: str
    ) -> Mapping[str, object]:
        if not workspace_id.strip() or not rule_id.strip() or not fingerprint.strip():
            raise ValueError("workspace_id, rule_id and fingerprint must be non-empty")
        payload = self._transport.request(
            "POST",
            f"/v1/workspaces/{quote(workspace_id, safe='')}/alerts/acknowledge",
            payload={"rule_id": rule_id, "fingerprint": fingerprint},
        )
        if not isinstance(payload, dict) or payload.get("rule_id") != rule_id:
            raise ProtocolError("alert acknowledgement response must contain matching rule_id")
        return payload

    def list_semantic_models(
        self, workspace_id: str, project_id: str
    ) -> tuple[dict[str, object], ...]:
        if not workspace_id.strip() or not project_id.strip():
            raise ValueError("workspace_id and project_id must be non-empty")
        payload = self._transport.request(
            "GET",
            "/v1/workspaces/"
            f"{quote(workspace_id, safe='')}/projects/{quote(project_id, safe='')}/semantic/models",
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            raise ProtocolError("semantic models response must contain an items array")
        if not all(isinstance(item, dict) for item in payload["items"]):
            raise ProtocolError("semantic model items must be objects")
        return tuple(payload["items"])

    def query_semantic(
        self, workspace_id: str, project_id: str, query: Mapping[str, object]
    ) -> SemanticQueryResult:
        if not workspace_id.strip() or not project_id.strip():
            raise ValueError("workspace_id and project_id must be non-empty")
        payload = self._transport.request(
            "POST",
            "/v1/workspaces/"
            f"{quote(workspace_id, safe='')}/projects/{quote(project_id, safe='')}/semantic/query",
            payload=query,
        )
        if (
            not isinstance(payload, dict)
            or not isinstance(payload.get("columns"), list)
            or not isinstance(payload.get("rows"), list)
        ):
            raise ProtocolError("semantic query response must contain columns and rows arrays")
        columns: list[SqlColumn] = []
        for item in payload["columns"]:
            if (
                not isinstance(item, dict)
                or not isinstance(item.get("name"), str)
                or not isinstance(item.get("type"), str)
            ):
                raise ProtocolError("semantic query columns are invalid")
            columns.append(SqlColumn(item["name"], item["type"]))
        rows = tuple(tuple(row) for row in payload["rows"] if isinstance(row, list))
        if len(rows) != len(payload["rows"]):
            raise ProtocolError("semantic query rows must be arrays")
        return SemanticQueryResult(tuple(columns), rows)

    def join_semantic(
        self,
        workspace_id: str,
        project_id: str,
        payload: Mapping[str, object],
    ) -> SemanticQueryResult:
        if not workspace_id.strip() or not project_id.strip():
            raise ValueError("workspace_id and project_id must be non-empty")
        if not isinstance(payload, Mapping):
            raise ValueError("semantic join payload must be an object")
        result = self._transport.request(
            "POST",
            f"/v1/workspaces/{quote(workspace_id, safe='')}/projects/"
            f"{quote(project_id, safe='')}/semantic/join",
            payload=dict(payload),
        )
        if not isinstance(result, dict):
            raise ProtocolError("semantic join response must be an object")
        columns = result.get("columns")
        rows = result.get("rows")
        if not isinstance(columns, list) or not isinstance(rows, list):
            raise ProtocolError("semantic join response must contain columns and rows arrays")
        if not all(
            isinstance(item, dict)
            and isinstance(item.get("name"), str)
            and isinstance(item.get("type"), str)
            for item in columns
        ):
            raise ProtocolError("semantic join columns are invalid")
        if not all(isinstance(row, list) for row in rows):
            raise ProtocolError("semantic join rows must be arrays")
        return SemanticQueryResult(
            tuple(SqlColumn(item["name"], item["type"]) for item in columns),
            tuple(tuple(row) for row in rows),
        )

    def query_graph(
        self, workspace_id: str, graph_id: str, query: str, *, max_limit: int = 1000
    ) -> Mapping[str, object]:
        if not workspace_id.strip() or not graph_id.strip() or not query.strip():
            raise ValueError("workspace_id, graph_id and query must be non-empty")
        if isinstance(max_limit, bool) or not 1 <= max_limit <= 10_000:
            raise ValueError("max_limit must be between 1 and 10000")
        return self._graph_request(
            workspace_id,
            graph_id,
            "query",
            {"query": query, "max_limit": max_limit},
        )

    def list_graph_objects(
        self, workspace_id: str, graph_id: str, object_type: str, *, limit: int = 100
    ) -> tuple[Mapping[str, object], ...]:
        if not workspace_id.strip() or not graph_id.strip() or not object_type.strip():
            raise ValueError("workspace_id, graph_id and object_type must be non-empty")
        if isinstance(limit, bool) or not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        payload = self._transport.request(
            "GET",
            f"/v1/workspaces/{quote(workspace_id, safe='')}/graphs/"
            f"{quote(graph_id, safe='')}/objects/{quote(object_type, safe='')}",
            query={"limit": str(limit)},
        )
        return self._graph_items(payload)

    def graph_neighbors(
        self,
        workspace_id: str,
        graph_id: str,
        object_type: str,
        key: list[object],
        *,
        limit: int = 100,
    ) -> tuple[Mapping[str, object], ...]:
        if not workspace_id.strip() or not graph_id.strip() or not object_type.strip():
            raise ValueError("workspace_id, graph_id and object_type must be non-empty")
        if isinstance(limit, bool) or not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        payload = self._transport.request(
            "POST",
            f"/v1/workspaces/{quote(workspace_id, safe='')}/graphs/"
            f"{quote(graph_id, safe='')}/neighbors",
            payload={"object_type": object_type, "key": key, "limit": limit},
        )
        return self._graph_items(payload)

    def execute_graph_action(
        self, workspace_id: str, graph_id: str, payload: Mapping[str, object]
    ) -> Mapping[str, object]:
        if not workspace_id.strip() or not graph_id.strip():
            raise ValueError("workspace_id and graph_id must be non-empty")
        result = self._transport.request(
            "POST",
            f"/v1/workspaces/{quote(workspace_id, safe='')}/graphs/"
            f"{quote(graph_id, safe='')}/actions",
            payload=dict(payload),
        )
        if not isinstance(result, dict):
            raise ProtocolError("graph action response must be an object")
        return result

    def list_ontology_versions(
        self, workspace_id: str, ontology_id: str
    ) -> tuple[Mapping[str, object], ...]:
        if not workspace_id.strip() or not ontology_id.strip():
            raise ValueError("workspace_id and ontology_id must be non-empty")
        payload = self._transport.request(
            "GET",
            f"/v1/workspaces/{quote(workspace_id, safe='')}/ontologies/"
            f"{quote(ontology_id, safe='')}",
        )
        return self._graph_items(payload)

    def get_ontology_schema(
        self, workspace_id: str, ontology_id: str, version: str
    ) -> Mapping[str, object]:
        if not workspace_id.strip() or not ontology_id.strip() or not version.strip():
            raise ValueError("workspace_id, ontology_id and version must be non-empty")
        payload = self._transport.request(
            "GET",
            f"/v1/workspaces/{quote(workspace_id, safe='')}/ontologies/"
            f"{quote(ontology_id, safe='')}/{quote(version, safe='')}",
        )
        if not isinstance(payload, dict):
            raise ProtocolError("ontology schema response must be an object")
        return payload

    def _graph_request(
        self, workspace_id: str, graph_id: str, operation: str, payload: Mapping[str, object]
    ) -> Mapping[str, object]:
        result = self._transport.request(
            "POST",
            f"/v1/workspaces/{quote(workspace_id, safe='')}/graphs/"
            f"{quote(graph_id, safe='')}/{operation}",
            payload=dict(payload),
        )
        if not isinstance(result, dict):
            raise ProtocolError("graph query response must be an object")
        return result

    @staticmethod
    def _graph_items(payload: object) -> tuple[Mapping[str, object], ...]:
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            raise ProtocolError("graph response must contain an items array")
        if not all(isinstance(item, dict) for item in payload["items"]):
            raise ProtocolError("graph items must be objects")
        return tuple(payload["items"])

    def list_semantic_dashboards(
        self, workspace_id: str, project_id: str
    ) -> tuple[dict[str, object], ...]:
        if not workspace_id.strip() or not project_id.strip():
            raise ValueError("workspace_id and project_id must be non-empty")
        payload = self._transport.request(
            "GET",
            "/v1/workspaces/"
            f"{quote(workspace_id, safe='')}/projects/"
            f"{quote(project_id, safe='')}/semantic/dashboards",
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            raise ProtocolError("semantic dashboards response must contain an items array")
        if not all(isinstance(item, dict) for item in payload["items"]):
            raise ProtocolError("semantic dashboard items must be objects")
        return tuple(payload["items"])

    def execute_semantic_dashboard(
        self, workspace_id: str, project_id: str, dashboard_id: str
    ) -> Mapping[str, object]:
        if not workspace_id.strip() or not project_id.strip() or not dashboard_id.strip():
            raise ValueError("workspace_id, project_id and dashboard_id must be non-empty")
        payload = self._transport.request(
            "POST",
            "/v1/workspaces/"
            f"{quote(workspace_id, safe='')}/projects/"
            f"{quote(project_id, safe='')}/semantic/dashboards/"
            f"{quote(dashboard_id, safe='')}/execute",
        )
        if (
            not isinstance(payload, dict)
            or payload.get("dashboard_id") != dashboard_id
            or not isinstance(payload.get("tiles"), list)
        ):
            raise ProtocolError(
                "semantic dashboard response must contain matching dashboard_id and tiles"
            )
        return payload

    def get_semantic_dashboard(
        self, workspace_id: str, project_id: str, dashboard_id: str
    ) -> Mapping[str, object]:
        if not workspace_id.strip() or not project_id.strip() or not dashboard_id.strip():
            raise ValueError("workspace_id, project_id and dashboard_id must be non-empty")
        payload = self._transport.request(
            "GET",
            "/v1/workspaces/"
            f"{quote(workspace_id, safe='')}/projects/"
            f"{quote(project_id, safe='')}/semantic/dashboards/"
            f"{quote(dashboard_id, safe='')}",
        )
        if not isinstance(payload, dict) or payload.get("id") != dashboard_id:
            raise ProtocolError("semantic dashboard response must contain matching id")
        return payload

    def platform_plugins(self) -> PlatformPlugins:
        """Return ready plugin and operation metadata advertised by the host."""
        payload = self._transport.request("GET", "/v1/platform/plugins")
        if not isinstance(payload, dict):
            raise ProtocolError("platform plugins response must be an object")
        raw_items = payload.get("items")
        raw_surfaces = payload.get("surfaces", [])
        raw_cli = payload.get("cli", [])
        raw_operations = payload.get("client_operations", [])
        if not all(
            isinstance(value, list) for value in (raw_items, raw_surfaces, raw_cli, raw_operations)
        ):
            raise ProtocolError("platform plugin metadata collections must be arrays")
        items: list[PluginInfo] = []
        for item in raw_items:
            if not isinstance(item, dict):
                raise ProtocolError("plugin metadata item must be an object")
            identifier = item.get("id")
            version = item.get("version")
            state = item.get("state")
            error = item.get("error")
            if not all(isinstance(value, str) and value for value in (identifier, version, state)):
                raise ProtocolError("plugin metadata identifiers must be non-empty strings")
            if error is not None and not isinstance(error, str):
                raise ProtocolError("plugin metadata error must be a string or null")
            items.append(PluginInfo(identifier, version, state, error))
        surfaces: list[PluginSurface] = []
        for item in raw_surfaces:
            if not isinstance(item, dict):
                raise ProtocolError("plugin surface must be an object")
            fields = (
                "id",
                "plugin_id",
                "namespace",
                "command",
                "operation_id",
                "capability",
                "permission",
                "transport",
                "api_version",
                "path",
                "method",
            )
            values = tuple(item.get(field) for field in fields)
            if not all(isinstance(value, str) and value for value in values):
                raise ProtocolError("plugin surface fields must be non-empty strings")
            surfaces.append(PluginSurface(*values))
        cli: list[PluginCliContribution] = []
        for item in raw_cli:
            if not isinstance(item, dict) or not all(
                isinstance(item.get(field), str) and item.get(field)
                for field in ("id", "namespace", "command", "operation_id")
            ):
                raise ProtocolError("plugin CLI contribution has invalid fields")
            options = item.get("options", [])
            if not isinstance(options, list) or not all(
                isinstance(value, str) for value in options
            ):
                raise ProtocolError("plugin CLI contribution options must be strings")
            cli.append(
                PluginCliContribution(
                    item["id"],
                    item["namespace"],
                    item["command"],
                    item["operation_id"],
                    tuple(options),
                )
            )
        operations: list[PluginClientOperation] = []
        for item in raw_operations:
            if not isinstance(item, dict):
                raise ProtocolError("plugin client operation must be an object")
            fields = ("id", "operation_id", "transport", "path", "method")
            values = tuple(item.get(field) for field in fields)
            if not all(isinstance(value, str) for value in values):
                raise ProtocolError("plugin client operation fields must be strings")
            operations.append(PluginClientOperation(*values))
        return PlatformPlugins(tuple(items), tuple(surfaces), tuple(cli), tuple(operations))

    def platform_connectors(self) -> Mapping[str, object]:
        """Return the provider-neutral connector capability registry."""
        payload = self._transport.request("GET", "/v1/platform/connectors")
        if not isinstance(payload, dict):
            raise ProtocolError("platform connectors response must be an object")
        return payload

    def preview_connector(self, definition: Mapping[str, object]) -> Mapping[str, object]:
        """Return a bounded connector preview and its checkpoint/sync evidence."""
        if not isinstance(definition, Mapping) or not definition:
            raise ValueError("definition must be a non-empty mapping")
        payload = self._transport.request(
            "POST", "/v1/platform/connectors/preview", payload=dict(definition)
        )
        if not isinstance(payload, dict) or payload.get("schema") != "ronin.ingestion-preview/v1":
            raise ProtocolError("connector preview response has an invalid schema")
        if not isinstance(payload.get("rows"), list) or not isinstance(payload.get("plan"), dict):
            raise ProtocolError("connector preview response must contain rows and plan")
        return payload

    def plan_connector(self, definition: Mapping[str, object]) -> Mapping[str, object]:
        """Validate a connector sync definition without reading source data."""
        if not isinstance(definition, Mapping) or not definition:
            raise ValueError("definition must be a non-empty mapping")
        payload = self._transport.request(
            "POST", "/v1/platform/connectors/plan", payload=dict(definition)
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("plan"), dict):
            raise ProtocolError("connector plan response must contain a plan")
        return payload

    def connector_checkpoint_health(self, checkpoint_identity: str) -> Mapping[str, object]:
        """Return durable health for a connector checkpoint identity."""
        if not checkpoint_identity.strip():
            raise ValueError("checkpoint_identity must be non-empty")
        payload = self._transport.request(
            "POST",
            "/v1/platform/connectors/checkpoint-health",
            payload={"checkpoint_identity": checkpoint_identity},
        )
        if not isinstance(payload, dict) or payload.get("identity") != checkpoint_identity:
            raise ProtocolError("connector checkpoint health response has invalid identity")
        return payload

    def plugin(self, namespace: str) -> PluginClient:
        if not namespace or namespace != namespace.strip() or " " in namespace:
            raise ValueError("plugin namespace must be non-empty and trimmed")
        return PluginClient(self, namespace)

    def get_job(self, job_id: str) -> Job:
        return _parse_job(self._transport.request("GET", f"/v1/jobs/{quote(job_id, safe='')}"))

    def list_jobs(
        self,
        *,
        project: str | None = None,
        state: JobState | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> JobPage:
        query: dict[str, str] = {"limit": str(limit)}
        if project is not None:
            if not project.strip():
                raise ValueError("project must be non-empty when supplied")
            query["project"] = project
        if state is not None:
            query["state"] = state.value
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        _validate_cursor(cursor, name="cursor")
        if cursor is not None:
            query["cursor"] = cursor
        return _parse_job_page(self._transport.request("GET", "/v1/jobs", query=query))

    def get_events(
        self,
        job_id: str,
        *,
        since: str | None = None,
        limit: int = 50,
    ) -> JobEventPage:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        _validate_cursor(since, name="since")
        query = {"limit": str(limit)}
        if since is not None:
            query["since"] = since
        return _parse_event_page(
            self._transport.request("GET", f"/v1/jobs/{quote(job_id, safe='')}/events", query=query)
        )

    def get_evidence(self, job_id: str) -> tuple[EvidenceReference, ...]:
        payload = self._transport.request("GET", f"/v1/jobs/{quote(job_id, safe='')}/evidence")
        if not isinstance(payload, dict) or set(payload) != {"items"}:
            raise ProtocolError("Evidence response must contain exactly items")
        items = payload["items"]
        if not isinstance(items, list):
            raise ProtocolError("Evidence response items must be a list")
        return tuple(_parse_evidence(item) for item in items)

    def _cancel_job(self, job_id: str) -> Job:
        return _parse_job(
            self._transport.request("POST", f"/v1/jobs/{quote(job_id, safe='')}/cancel")
        )


@dataclass(frozen=True, slots=True)
class JobHandle:
    client: Ronin
    id: str

    def status(self) -> JobState:
        return self.client.get_job(self.id).state

    def wait(self, *, poll_interval: float = 1.0, timeout: float | None = None) -> Job:
        if poll_interval <= 0:
            raise ValueError("poll_interval must be positive")
        if timeout is not None and timeout <= 0:
            raise ValueError("timeout must be positive")
        started = time.monotonic()
        while True:
            job = self.client.get_job(self.id)
            if job.state.terminal:
                return job
            if timeout is not None and time.monotonic() - started >= timeout:
                raise TimeoutError(f"Timed out waiting for Ronin job {self.id}")
            time.sleep(poll_interval)

    def cancel(self) -> Job:
        return self.client._cancel_job(self.id)

    def events(self, *, since: str | None = None, limit: int = 50) -> JobEventPage:
        return self.client.get_events(self.id, since=since, limit=limit)

    def evidence(self) -> tuple[EvidenceReference, ...]:
        return self.client.get_evidence(self.id)


def _parse_job(payload: object) -> Job:
    if not isinstance(payload, dict) or set(payload) != _JOB_FIELDS:
        raise ProtocolError("Job fields do not match the v1 contract")
    job_id = payload["id"]
    state = payload["state"]
    if not isinstance(job_id, str) or not job_id or job_id != job_id.strip() or len(job_id) > 256:
        raise ProtocolError("Job id must be a bounded non-empty string")
    if not isinstance(state, str):
        raise ProtocolError("Job state must be a string")
    try:
        job_state = JobState(state)
    except ValueError as exc:
        raise ProtocolError(f"Unknown job state {state!r}") from exc
    failure_code = payload["failure_code"]
    if failure_code is not None and not isinstance(failure_code, str):
        raise ProtocolError("failure_code must be a string when present")
    return Job(job_id, job_state, failure_code)


def _parse_sql_result(payload: object) -> SqlResult:
    if not isinstance(payload, dict) or set(payload) != {"columns", "rows"}:
        raise ProtocolError("SQL result must contain exactly columns and rows")
    columns = payload["columns"]
    rows = payload["rows"]
    if not isinstance(columns, list) or not isinstance(rows, list):
        raise ProtocolError("SQL result columns and rows must be arrays")
    parsed_columns: list[SqlColumn] = []
    for column in columns:
        if not isinstance(column, dict) or set(column) != _SQL_COLUMN_FIELDS:
            raise ProtocolError("SQL result column has invalid shape")
        name, type_name = column["name"], column["type"]
        if not isinstance(name, str) or not name or not isinstance(type_name, str) or not type_name:
            raise ProtocolError("SQL result column fields must be non-empty strings")
        parsed_columns.append(SqlColumn(name, type_name))
    width = len(parsed_columns)
    parsed_rows: list[tuple[object, ...]] = []
    for row in rows:
        if not isinstance(row, list) or len(row) != width:
            raise ProtocolError("SQL result row width does not match columns")
        parsed_rows.append(tuple(row))
    return SqlResult(tuple(parsed_columns), tuple(parsed_rows))


def _parse_job_page(payload: object) -> JobPage:
    if not isinstance(payload, dict) or set(payload) != {"items", "next_cursor"}:
        raise ProtocolError("Job page must contain exactly items and next_cursor")
    items = payload["items"]
    if not isinstance(items, list):
        raise ProtocolError("Job page items must be a list")
    next_cursor = _parse_cursor(payload["next_cursor"], name="next_cursor", nullable=True)
    return JobPage(tuple(_parse_job(item) for item in items), next_cursor)


def _parse_event(payload: object) -> JobEvent:
    if not isinstance(payload, dict) or set(payload) != _EVENT_FIELDS:
        raise ProtocolError("Job event fields do not match the v1 contract")
    sequence = payload["sequence"]
    attempt_id = payload["attempt_id"]
    attempt_sequence = payload["attempt_sequence"]
    kind = payload["kind"]
    message = payload["message"]
    occurred_at = payload["occurred_at"]
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 0:
        raise ProtocolError("Job event sequence must be a non-negative integer")
    if not isinstance(attempt_id, str) or not attempt_id or len(attempt_id) > 256:
        raise ProtocolError("Job event attempt_id must be a bounded non-empty string")
    if (
        not isinstance(attempt_sequence, int)
        or isinstance(attempt_sequence, bool)
        or attempt_sequence < 0
    ):
        raise ProtocolError("Job event attempt_sequence must be a non-negative integer")
    if not isinstance(kind, str) or not kind:
        raise ProtocolError("Job event kind must be a non-empty string")
    if not isinstance(message, str):
        raise ProtocolError("Job event message must be a string")
    if not isinstance(occurred_at, str) or _INSTANT_RE.fullmatch(occurred_at) is None:
        raise ProtocolError("Job event occurred_at must be a canonical Instant")
    return JobEvent(sequence, attempt_id, attempt_sequence, kind, message, occurred_at)


def _parse_event_page(payload: object) -> JobEventPage:
    if not isinstance(payload, dict) or set(payload) != {"items", "next_since"}:
        raise ProtocolError("Job event page must contain exactly items and next_since")
    items = payload["items"]
    if not isinstance(items, list):
        raise ProtocolError("Job event page items must be a list")
    next_since = _parse_cursor(payload["next_since"], name="next_since", nullable=False)
    if next_since is None:
        raise ProtocolError("next_since must be present")
    return JobEventPage(tuple(_parse_event(item) for item in items), next_since)


def _parse_evidence(payload: object) -> EvidenceReference:
    if not isinstance(payload, dict) or set(payload) != _EVIDENCE_FIELDS:
        raise ProtocolError("Evidence fields do not match the v1 contract")
    if payload["version"] != 1:
        raise ProtocolError("Unsupported evidence version")
    cell_id = payload["cell_id"]
    role = payload["role"]
    digest_algorithm = payload["digest_algorithm"]
    digest = payload["digest"]
    media_type = payload["media_type"]
    size_bytes = payload["size_bytes"]
    availability_raw = payload["availability"]
    reason = payload["reason"]
    if cell_id is not None and (not isinstance(cell_id, str) or not cell_id):
        raise ProtocolError("Evidence cell_id must be a non-empty string when present")
    if not isinstance(role, str) or not role:
        raise ProtocolError("Evidence role must be a non-empty string")
    if not isinstance(availability_raw, str):
        raise ProtocolError("Evidence availability must be a string")
    try:
        availability = EvidenceAvailability(availability_raw)
    except ValueError as exc:
        raise ProtocolError("Unknown evidence availability") from exc
    if media_type is not None and not isinstance(media_type, str):
        raise ProtocolError("Evidence media_type must be a string when present")
    if reason is not None and not isinstance(reason, str):
        raise ProtocolError("Evidence reason must be a string when present")
    identity = (digest_algorithm, digest, size_bytes)
    if availability is EvidenceAvailability.UNAVAILABLE:
        if any(value is not None for value in identity) or reason is None or not reason:
            raise ProtocolError("Unavailable evidence must omit identity and carry a reason")
    else:
        if not isinstance(digest_algorithm, str) or digest_algorithm != "sha256":
            raise ProtocolError("Evidence digest_algorithm must be sha256")
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(ch not in "0123456789abcdef" for ch in digest)
        ):
            raise ProtocolError("Evidence digest must be lowercase SHA-256 hex")
        if not isinstance(size_bytes, int) or isinstance(size_bytes, bool) or size_bytes < 0:
            raise ProtocolError("Evidence size_bytes must be a non-negative integer")
        if reason is not None:
            raise ProtocolError("Only unavailable evidence may carry a reason")
    return EvidenceReference(
        1, cell_id, role, digest_algorithm, digest, media_type, size_bytes, availability, reason
    )


__all__ = [
    "APIError",
    "CatalogAsset",
    "CatalogLineageEdge",
    "DeploymentBinding",
    "GlossaryTerm",
    "OwnershipMetadata",
    "SensitivityMetadata",
    "EvidenceAvailability",
    "EvidenceReference",
    "HTTPTransport",
    "Job",
    "JobEvent",
    "JobEventPage",
    "JobHandle",
    "JobPage",
    "JobState",
    "PlatformPlugins",
    "PluginCliContribution",
    "PluginClientOperation",
    "PluginInfo",
    "PluginSurface",
    "ProjectEnvironmentBindings",
    "ProtocolError",
    "Ronin",
    "SqlColumn",
    "SqlResult",
    "StreamingHealth",
    "SemanticQueryResult",
    "RoninError",
    "Transport",
    "TransportError",
    "__version__",
]
