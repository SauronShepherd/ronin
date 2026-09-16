"""Single-workspace OIDC administration surface for security provisioning."""

from __future__ import annotations

import sqlite3
from http import HTTPStatus
from typing import Protocol, cast, runtime_checkable
from urllib.parse import unquote, urlsplit

from studio_core import WorkspaceId
from studio_execution import DurableExecutionService
from studio_security import (
    Group,
    GroupId,
    IdentityConflict,
    OidcPrincipalStore,
    OidcTokenValidator,
    Principal,
    PrincipalId,
    PrincipalKind,
    RbacStore,
    RoleBinding,
    SubjectKind,
    WorkspaceRole,
)

from studio_server.oidc_http import (
    AuthorizationAuditError,
    AuthorizationAuditStore,
    OidcRoninHTTPServer,
    OidcWorkspaceStore,
    _OidcHandler,
)

_ADMIN_PREFIX = "/v1/admin/security/"
_MAX_IDENTIFIER_CHARS = 256


@runtime_checkable
class SecurityAdminStore(OidcPrincipalStore, RbacStore, Protocol):
    def put_principal(self, principal: Principal) -> Principal: ...

    def get_principal(self, principal_id: PrincipalId) -> Principal | None: ...

    def put_group(self, group: Group) -> Group: ...

    def add_group_member(self, group_id: GroupId, principal_id: PrincipalId) -> None: ...

    def remove_group_member(self, group_id: GroupId, principal_id: PrincipalId) -> bool: ...

    def put_role_binding(self, binding: RoleBinding) -> RoleBinding: ...

    def delete_role_binding(self, binding: RoleBinding) -> bool: ...


def _segment(value: str, name: str) -> str:
    try:
        decoded = unquote(value, errors="strict")
    except UnicodeError as exc:
        raise ValueError(f"{name} is invalid") from exc
    if (
        not decoded
        or decoded != decoded.strip()
        or "/" in decoded
        or "\x00" in decoded
        or len(decoded) > _MAX_IDENTIFIER_CHARS
    ):
        raise ValueError(f"{name} is invalid")
    return decoded


def _principal_payload(principal: Principal) -> dict[str, object]:
    return {
        "id": principal.id.value,
        "kind": principal.kind,
        "display_name": principal.display_name,
        "issuer": principal.issuer,
        "subject": principal.subject,
        "email": principal.email,
        "active": principal.active,
    }


def _group_payload(group: Group) -> dict[str, str]:
    return {"id": group.id.value, "name": group.name}


def _binding_payload(binding: RoleBinding) -> dict[str, object]:
    return {
        "workspace_id": binding.workspace_id.value,
        "subject_kind": binding.subject_kind,
        "subject_id": binding.subject_id,
        "role": binding.role,
    }


class _OidcAdminHandler(_OidcHandler):
    def _admin_server(self) -> OidcAdminRoninHTTPServer:
        return cast(OidcAdminRoninHTTPServer, self.server)

    def _require_admin(self, resource_ref: str) -> bool:
        actor = self._actor
        if actor is None:
            self._error(
                HTTPStatus.UNAUTHORIZED,
                "unauthorized",
                "valid OIDC bearer authorization required",
            )
            return False
        try:
            decision = self._admin_server().authorize(
                actor,
                "workspace.admin",
                resource_ref=resource_ref,
                request_id=self._request_id,
            )
        except AuthorizationAuditError:
            self._error(
                HTTPStatus.SERVICE_UNAVAILABLE,
                "authorization_audit_unavailable",
                "authorization decision could not be durably audited",
            )
            return False
        if decision.allowed:
            return True
        self._error(
            HTTPStatus.FORBIDDEN,
            "forbidden",
            "workspace.admin permission is required",
        )
        return False

    def _empty_body_required(self) -> bool:
        length = self.headers.get("Content-Length")
        if length in {None, "0"}:
            return True
        self._error(
            HTTPStatus.BAD_REQUEST,
            "invalid_request",
            "request body must be empty for this route",
        )
        return False

    def _admin_path(self) -> tuple[str, ...] | None:
        split = urlsplit(self.path)
        if not split.path.startswith(_ADMIN_PREFIX):
            return None
        if split.query:
            self._error(
                HTTPStatus.BAD_REQUEST,
                "invalid_request",
                "admin mutation routes do not accept query parameters",
            )
            return ()
        raw = split.path[len(_ADMIN_PREFIX) :]
        if not raw:
            self._error(HTTPStatus.NOT_FOUND, "not_found", "route not found")
            return ()
        return tuple(raw.split("/"))

    def _put_principal(self, encoded_id: str) -> None:
        try:
            principal_id = PrincipalId(_segment(encoded_id, "principal id"))
            if not self._require_admin(f"security:principal:{principal_id.value}"):
                return
            payload = self._read_json()
            if not isinstance(payload, dict):
                raise ValueError("request body must be a JSON object")
            allowed = {"kind", "display_name", "issuer", "subject", "email", "active"}
            if set(payload) - allowed:
                raise ValueError("request body contains unknown fields")
            if not {"kind", "display_name", "issuer", "subject"}.issubset(payload):
                raise ValueError("principal body is missing required fields")
            kind = payload["kind"]
            display_name = payload["display_name"]
            issuer = payload["issuer"]
            subject = payload["subject"]
            email = payload.get("email")
            active = payload.get("active", True)
            if kind not in {"user", "service"}:
                raise ValueError("principal kind must be user or service")
            if not all(isinstance(value, str) for value in (display_name, issuer, subject)):
                raise ValueError("principal display_name, issuer and subject must be strings")
            if email is not None and not isinstance(email, str):
                raise ValueError("principal email must be a string or null")
            if not isinstance(active, bool):
                raise ValueError("principal active must be boolean")
            principal = Principal(
                principal_id,
                cast(PrincipalKind, kind),
                cast(str, display_name),
                cast(str, issuer),
                cast(str, subject),
                cast(str | None, email),
                active,
            )
            existed = self._admin_server().admin_store.get_principal(principal_id) is not None
            stored = self._admin_server().admin_store.put_principal(principal)
        except IdentityConflict:
            self._error(
                HTTPStatus.CONFLICT,
                "identity_conflict",
                "principal identity conflicts with existing stable identity",
            )
            return
        except ValueError as exc:
            self._error(HTTPStatus.BAD_REQUEST, "invalid_request", str(exc))
            return
        self._write_json(HTTPStatus.OK if existed else HTTPStatus.CREATED, _principal_payload(stored))

    def _put_group(self, encoded_id: str) -> None:
        try:
            group_id = GroupId(_segment(encoded_id, "group id"))
            if not self._require_admin(f"security:group:{group_id.value}"):
                return
            payload = self._read_json()
            if not isinstance(payload, dict) or set(payload) != {"name"}:
                raise ValueError("group body must contain exactly name")
            name = payload["name"]
            if not isinstance(name, str):
                raise ValueError("group name must be a string")
            stored = self._admin_server().admin_store.put_group(Group(group_id, name))
        except ValueError as exc:
            self._error(HTTPStatus.BAD_REQUEST, "invalid_request", str(exc))
            return
        self._write_json(HTTPStatus.OK, _group_payload(stored))

    def _put_member(self, encoded_group: str, encoded_principal: str) -> None:
        try:
            group_id = GroupId(_segment(encoded_group, "group id"))
            principal_id = PrincipalId(_segment(encoded_principal, "principal id"))
            if not self._require_admin(
                f"security:group:{group_id.value}:member:{principal_id.value}"
            ):
                return
            if not self._empty_body_required():
                return
            if self._admin_server().admin_store.get_principal(principal_id) is None:
                self._error(HTTPStatus.NOT_FOUND, "principal_not_found", "principal does not exist")
                return
            self._admin_server().admin_store.add_group_member(group_id, principal_id)
        except sqlite3.IntegrityError:
            self._error(HTTPStatus.NOT_FOUND, "group_not_found", "group does not exist")
            return
        except ValueError as exc:
            self._error(HTTPStatus.BAD_REQUEST, "invalid_request", str(exc))
            return
        self._write_json(
            HTTPStatus.OK,
            {"group_id": group_id.value, "principal_id": principal_id.value, "member": True},
        )

    def _delete_member(self, encoded_group: str, encoded_principal: str) -> None:
        try:
            group_id = GroupId(_segment(encoded_group, "group id"))
            principal_id = PrincipalId(_segment(encoded_principal, "principal id"))
            if not self._require_admin(
                f"security:group:{group_id.value}:member:{principal_id.value}"
            ):
                return
            if not self._empty_body_required():
                return
            removed = self._admin_server().admin_store.remove_group_member(group_id, principal_id)
        except ValueError as exc:
            self._error(HTTPStatus.BAD_REQUEST, "invalid_request", str(exc))
            return
        self._write_json(
            HTTPStatus.OK,
            {"group_id": group_id.value, "principal_id": principal_id.value, "member": False, "removed": removed},
        )

    def _binding(self, encoded_kind: str, encoded_subject: str, encoded_role: str) -> RoleBinding:
        kind = _segment(encoded_kind, "subject kind")
        subject_id = _segment(encoded_subject, "subject id")
        role = _segment(encoded_role, "workspace role")
        return RoleBinding(
            self._admin_server().workspace_id,
            cast(SubjectKind, kind),
            subject_id,
            cast(WorkspaceRole, role),
        )

    def _put_binding(self, encoded_kind: str, encoded_subject: str, encoded_role: str) -> None:
        try:
            binding = self._binding(encoded_kind, encoded_subject, encoded_role)
            if not self._require_admin(
                f"security:role-binding:{binding.subject_kind}:{binding.subject_id}:{binding.role}"
            ):
                return
            if not self._empty_body_required():
                return
            stored = self._admin_server().admin_store.put_role_binding(binding)
        except KeyError:
            self._error(
                HTTPStatus.NOT_FOUND,
                "subject_not_found",
                "role binding subject does not exist",
            )
            return
        except ValueError as exc:
            self._error(HTTPStatus.BAD_REQUEST, "invalid_request", str(exc))
            return
        self._write_json(HTTPStatus.OK, _binding_payload(stored))

    def _delete_binding(self, encoded_kind: str, encoded_subject: str, encoded_role: str) -> None:
        try:
            binding = self._binding(encoded_kind, encoded_subject, encoded_role)
            if not self._require_admin(
                f"security:role-binding:{binding.subject_kind}:{binding.subject_id}:{binding.role}"
            ):
                return
            if not self._empty_body_required():
                return
            removed = self._admin_server().admin_store.delete_role_binding(binding)
        except ValueError as exc:
            self._error(HTTPStatus.BAD_REQUEST, "invalid_request", str(exc))
            return
        payload = _binding_payload(binding)
        payload["removed"] = removed
        self._write_json(HTTPStatus.OK, payload)

    def _authenticated_put(self) -> None:
        path = self._admin_path()
        if path is None:
            self._error(HTTPStatus.NOT_FOUND, "not_found", "route not found")
            return
        if not path:
            return
        if len(path) == 2 and path[0] == "principals":
            self._put_principal(path[1])
            return
        if len(path) == 2 and path[0] == "groups":
            self._put_group(path[1])
            return
        if len(path) == 4 and path[0] == "groups" and path[2] == "members":
            self._put_member(path[1], path[3])
            return
        if len(path) == 4 and path[0] == "role-bindings":
            self._put_binding(path[1], path[2], path[3])
            return
        self._error(HTTPStatus.NOT_FOUND, "not_found", "route not found")

    def _authenticated_delete(self) -> None:
        path = self._admin_path()
        if path is None:
            self._error(HTTPStatus.NOT_FOUND, "not_found", "route not found")
            return
        if not path:
            return
        if len(path) == 4 and path[0] == "groups" and path[2] == "members":
            self._delete_member(path[1], path[3])
            return
        if len(path) == 4 and path[0] == "role-bindings":
            self._delete_binding(path[1], path[2], path[3])
            return
        self._error(HTTPStatus.NOT_FOUND, "not_found", "route not found")

    def _method_not_allowed(self) -> None:
        self._error(
            HTTPStatus.METHOD_NOT_ALLOWED,
            "method_not_allowed",
            "method is not supported for this admin route",
        )

    def do_PUT(self) -> None:  # noqa: N802
        self._dispatch_authenticated(self._authenticated_put)

    def do_DELETE(self) -> None:  # noqa: N802
        self._dispatch_authenticated(self._authenticated_delete)

    def do_PATCH(self) -> None:  # noqa: N802
        if urlsplit(self.path).path.startswith(_ADMIN_PREFIX):
            self._dispatch_authenticated(self._method_not_allowed)
            return
        self._error(HTTPStatus.NOT_FOUND, "not_found", "route not found")

    def do_POST(self) -> None:  # noqa: N802
        if urlsplit(self.path).path.startswith(_ADMIN_PREFIX):
            self._dispatch_authenticated(self._method_not_allowed)
            return
        super().do_POST()

    def do_GET(self) -> None:  # noqa: N802
        if urlsplit(self.path).path.startswith(_ADMIN_PREFIX):
            self._dispatch_authenticated(self._method_not_allowed)
            return
        super().do_GET()


class OidcAdminRoninHTTPServer(OidcRoninHTTPServer):
    """OIDC Job server plus explicit single-workspace security administration routes."""

    def __init__(
        self,
        server_address: tuple[str, int],
        service: DurableExecutionService,
        *,
        workspace_id: WorkspaceId,
        validator: OidcTokenValidator,
        admin_store: SecurityAdminStore,
        workspace_store: OidcWorkspaceStore,
        audit_store: AuthorizationAuditStore,
    ) -> None:
        self._admin_store = admin_store
        super().__init__(
            server_address,
            service,
            workspace_id=workspace_id,
            validator=validator,
            principal_store=admin_store,
            rbac_store=admin_store,
            workspace_store=workspace_store,
            audit_store=audit_store,
        )
        self.RequestHandlerClass = _OidcAdminHandler

    @property
    def admin_store(self) -> SecurityAdminStore:
        return self._admin_store


__all__ = ("OidcAdminRoninHTTPServer", "SecurityAdminStore")
