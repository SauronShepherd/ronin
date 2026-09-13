"""Opt-in OIDC + workspace-RBAC profile for the existing public Job HTTP contract."""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Protocol, cast, runtime_checkable
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from studio_core import Action, ProjectId, WorkspaceId
from studio_core.audit import AuditEvent
from studio_execution import DurableExecutionService
from studio_orchestrator import Instant, Job
from studio_security import (
    Actor,
    OidcAuthenticationError,
    OidcPrincipalStore,
    OidcTokenValidator,
    Permission,
    PolicyDecision,
    PolicyRequirement,
    RbacAuthorizer,
    RbacStore,
    actor_context,
    authorization_audit_event,
)
from studio_storage import sqlite_ready

from studio_server.http import DurableHTTPApplication, _Handler
from studio_server.transport_policy import (
    allows_plaintext_non_loopback,
    is_loopback_host,
    parse_bind_policy,
)

_BIND_POLICY_ENV = "RONIN_BIND_POLICY"


@runtime_checkable
class OidcWorkspaceStore(Protocol):
    def get_project(self, workspace_id: WorkspaceId, project_id: ProjectId) -> object | None: ...


@runtime_checkable
class AuthorizationAuditStore(Protocol):
    def append(self, workspace_id: WorkspaceId, event: AuditEvent) -> AuditEvent: ...


class AuthorizationAuditError(RuntimeError):
    """Raised when an authorization decision cannot be durably audited."""


def _now() -> Instant:
    return Instant(datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ"))


def _readiness_database_from_env() -> Path:
    return Path(os.environ.get("RONIN_DB", ".ronin/ronin.sqlite3")).expanduser().resolve()


def _permission_for_action(action: Action) -> Permission:
    if action in {"submit", "execute"}:
        return "job.submit"
    if action == "cancel":
        return "job.cancel"
    if action in {"read", "list", "events", "evidence:read"}:
        return "job.read"
    raise ValueError(f"unsupported Job HTTP authorization action: {action}")


class _OidcHandler(_Handler):
    _actor: Actor | None = None
    _request_id: str | None = None
    _decision_cache: dict[tuple[Permission, str], PolicyDecision]

    def _oidc_server(self) -> OidcRoninHTTPServer:
        return cast(OidcRoninHTTPServer, self.server)

    def _authenticate(self) -> Actor | None:
        authorization = self.headers.get("Authorization")
        prefix = "Bearer "
        if authorization is None or not authorization.startswith(prefix):
            self._error(HTTPStatus.UNAUTHORIZED, "unauthorized", "valid OIDC bearer authorization required")
            return None
        token = authorization[len(prefix) :]
        try:
            return self._oidc_server().authenticate(token)
        except OidcAuthenticationError:
            self._error(HTTPStatus.UNAUTHORIZED, "unauthorized", "valid OIDC bearer authorization required")
            return None

    def _require_auth(self) -> bool:
        if self._actor is not None:
            return True
        self._error(HTTPStatus.UNAUTHORIZED, "unauthorized", "valid OIDC bearer authorization required")
        return False

    def _project_registered(self, project_id: str) -> bool:
        try:
            registered = self._oidc_server().project_registered(project_id)
        except ValueError:
            registered = False
        if registered:
            return True
        self._error(HTTPStatus.NOT_FOUND, "project_not_found", "project does not exist in this workspace")
        return False

    def _authorize_project(self, action: Action, project_id: str) -> PolicyDecision | None:
        if self._actor is None:
            self._error(HTTPStatus.UNAUTHORIZED, "unauthorized", "valid OIDC bearer authorization required")
            return None
        if not self._project_registered(project_id):
            return None
        permission = _permission_for_action(action)
        key = (permission, project_id)
        cached = self._decision_cache.get(key)
        if cached is not None:
            return cached
        try:
            decision = self._oidc_server().authorize(
                self._actor,
                permission,
                resource_ref=f"project:{project_id}",
                request_id=self._request_id,
            )
        except AuthorizationAuditError:
            self._error(
                HTTPStatus.SERVICE_UNAVAILABLE,
                "authorization_audit_unavailable",
                "authorization decision could not be durably audited",
            )
            return None
        self._decision_cache[key] = decision
        return decision

    def _require_project(self, action: Action, project_id: str) -> bool:
        decision = self._authorize_project(action, project_id)
        if decision is None:
            return False
        if decision.allowed:
            return True
        self._error(HTTPStatus.FORBIDDEN, "forbidden", "required workspace permission is not granted")
        return False

    def _require_visible_job(self, action: Action, job: Job | None) -> Job | None:
        if job is None:
            self._error(HTTPStatus.NOT_FOUND, "job_not_found", "job does not exist")
            return None
        decision = self._authorize_project(action, job.project_id)
        if decision is not None and decision.allowed:
            return job
        if decision is not None:
            self._error(HTTPStatus.NOT_FOUND, "job_not_found", "job does not exist")
        return None

    def _dispatch_authenticated(self, method: Callable[[], None]) -> None:
        actor = self._authenticate()
        if actor is None:
            return
        self._actor = actor
        self._request_id = f"req-{uuid4().hex}"
        self._decision_cache = {}
        try:
            with actor_context(actor):
                method()
        finally:
            self._actor = None
            self._request_id = None
            self._decision_cache = {}

    def _authenticated_get(self) -> None:
        split = urlsplit(self.path)
        if split.path == "/v1/jobs":
            parsed = parse_qs(split.query, keep_blank_values=True, strict_parsing=False)
            if "project" not in parsed:
                self._error(
                    HTTPStatus.BAD_REQUEST,
                    "project_required",
                    "OIDC job listing requires an explicit project filter",
                )
                return
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch_authenticated(super().do_POST)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/healthz":
            ready = self._oidc_server().ready()
            self._write_json(
                HTTPStatus.OK if ready else HTTPStatus.SERVICE_UNAVAILABLE,
                {"status": "ready" if ready else "not_ready"},
            )
            return
        self._dispatch_authenticated(self._authenticated_get)


class OidcRoninHTTPServer(ThreadingHTTPServer):
    """Single-workspace OIDC server profile over the existing alpha Job API."""

    daemon_threads = True

    def __init__(
        self,
        server_address: tuple[str, int],
        service: DurableExecutionService,
        *,
        workspace_id: WorkspaceId,
        validator: OidcTokenValidator,
        principal_store: OidcPrincipalStore,
        rbac_store: RbacStore,
        workspace_store: OidcWorkspaceStore,
        audit_store: AuthorizationAuditStore,
    ) -> None:
        host, _port = server_address
        policy = parse_bind_policy(os.environ.get(_BIND_POLICY_ENV))
        if not is_loopback_host(host) and not allows_plaintext_non_loopback(policy):
            raise ValueError(
                "Ronin's built-in server is plaintext HTTP; non-loopback binding requires "
                "an explicitly permitted bind policy or an external TLS terminator"
            )
        self.application = DurableHTTPApplication(service)
        self._workspace_id = workspace_id
        self._validator = validator
        self._principal_store = principal_store
        self._authorizer = RbacAuthorizer(rbac_store)
        self._workspace_store = workspace_store
        self._audit_store = audit_store
        self._readiness_database = _readiness_database_from_env()
        try:
            super().__init__(server_address, _OidcHandler)
        except BaseException:
            self.application.close()
            raise

    @property
    def workspace_id(self) -> WorkspaceId:
        return self._workspace_id

    def authenticate(self, token: str) -> Actor:
        principal = self._validator.authenticate_principal(token, self._principal_store)
        return self._authorizer.actor(principal, auth_method="oidc")

    def project_registered(self, project_id: str) -> bool:
        project = ProjectId(project_id)
        return self._workspace_store.get_project(self._workspace_id, project) is not None

    def authorize(
        self,
        actor: Actor,
        permission: Permission,
        *,
        resource_ref: str,
        request_id: str | None,
    ) -> PolicyDecision:
        requirement = PolicyRequirement(self._workspace_id, permission, resource_ref)
        decision = self._authorizer.authorize(actor, requirement)
        event = authorization_audit_event(
            actor,
            requirement,
            decision,
            now=_now(),
            request_id=request_id,
        )
        try:
            self._audit_store.append(self._workspace_id, event)
        except Exception as exc:
            raise AuthorizationAuditError("authorization audit persistence failed") from exc
        return decision

    def ready(self) -> bool:
        return sqlite_ready(self._readiness_database)

    def server_close(self) -> None:
        try:
            super().server_close()
        finally:
            self.application.close()


__all__ = (
    "AuthorizationAuditError",
    "AuthorizationAuditStore",
    "OidcRoninHTTPServer",
    "OidcWorkspaceStore",
)
