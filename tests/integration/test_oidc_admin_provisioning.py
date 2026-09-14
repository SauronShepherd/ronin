from __future__ import annotations

import json
import time
from pathlib import Path
from threading import Thread

import pytest
from pyronin import APIError, HTTPTransport, Ronin
from studio_core import (
    ExecutionProfile,
    Project,
    ProjectId,
    ProjectManifest,
    RepositoryBinding,
    RuntimeProfileRef,
    Workspace,
    WorkspaceId,
)
from studio_execution import DurableExecutionService
from studio_orchestrator import Instant
from studio_security import (
    Group,
    GroupId,
    OidcConfig,
    OidcTokenValidator,
    Principal,
    PrincipalId,
    RoleBinding,
    SqliteIdentityStore,
)
from studio_server import OidcAdminRoninHTTPServer
from studio_storage import SqliteJobStore, SqliteWorkspaceStore
from studio_storage.audit import SqliteAuditStore

_NOW = Instant("2026-09-14T03:50:00.000000Z")
_WS = WorkspaceId("workspace-admin")
_PROJECT = ProjectId("project-admin")
_ISSUER = "https://issuer.example"
_AUDIENCE = "ronin"


class _Keys:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def jwks(self) -> dict[str, object]:
        return self._payload


class _FailingAuditStore:
    def append(self, workspace_id, event):
        del workspace_id, event
        raise RuntimeError("audit unavailable")


def _manifest() -> ProjectManifest:
    return ProjectManifest.from_project(
        Project(
            _PROJECT,
            "Admin project",
            (
                RepositoryBinding(
                    "code",
                    "https://git.example.test/team/admin.git",
                    role="primary",
                ),
            ),
            ExecutionProfile(runtime=RuntimeProfileRef("python", "3.11")),
        )
    )


def _principal(identifier: str, subject: str) -> Principal:
    return Principal(
        PrincipalId(identifier),
        "user",
        identifier.title(),
        _ISSUER,
        subject,
        f"{identifier}@example.test",
    )


def _oidc_material():
    jwt = pytest.importorskip("jwt")
    rsa = pytest.importorskip("cryptography.hazmat.primitives.asymmetric.rsa")
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    public_jwk["kid"] = "key-1"
    validator = OidcTokenValidator(
        OidcConfig(_ISSUER, _AUDIENCE, ("RS256",)),
        _Keys({"keys": [public_jwk]}),
    )

    def token(subject: str) -> str:
        now = int(time.time())
        return jwt.encode(
            {"iss": _ISSUER, "sub": subject, "aud": _AUDIENCE, "iat": now, "exp": now + 300},
            private_key,
            algorithm="RS256",
            headers={"kid": "key-1"},
        )

    return validator, token


def _start_server(monkeypatch, database: Path, *, audit_store=None):
    monkeypatch.setenv("RONIN_DB", str(database))
    validator, issue_token = _oidc_material()
    workspaces = SqliteWorkspaceStore(database, migration_now=_NOW)
    workspaces.create_workspace(Workspace(_WS, "Admin Workspace"), now=_NOW)
    workspaces.register_project(_WS, _manifest(), now=_NOW)
    identities = SqliteIdentityStore(database)
    audit = SqliteAuditStore(database, migration_now=_NOW)
    jobs = SqliteJobStore(database, migration_now=_NOW)
    service = DurableExecutionService(jobs)
    server = OidcAdminRoninHTTPServer(
        ("127.0.0.1", 0),
        service,
        workspace_id=_WS,
        validator=validator,
        admin_store=identities,
        workspace_store=workspaces,
        audit_store=audit if audit_store is None else audit_store,
    )
    thread = Thread(target=server.serve_forever, name="ronin-oidc-admin-test", daemon=True)
    thread.start()
    return server, thread, issue_token, identities, audit


def _transport(server: OidcAdminRoninHTTPServer, token: str) -> HTTPTransport:
    return HTTPTransport(
        f"http://127.0.0.1:{server.server_port}",
        token=token,
        allow_insecure_localhost=True,
        max_retries=0,
    )


def _close(server: OidcAdminRoninHTTPServer, thread: Thread) -> None:
    server.shutdown()
    server.server_close()
    thread.join(timeout=5.0)
    assert not thread.is_alive()


def test_admin_provisions_identity_group_membership_and_role_with_audit(
    monkeypatch, tmp_path: Path
) -> None:
    server, thread, issue_token, identities, audit = _start_server(
        monkeypatch, tmp_path / "ronin.sqlite3"
    )
    admin = identities.put_principal(_principal("admin", "admin-sub"))
    identities.put_role_binding(RoleBinding(_WS, "principal", admin.id.value, "admin"))
    transport = _transport(server, issue_token("admin-sub"))

    try:
        created = transport.request(
            "PUT",
            "/v1/admin/security/principals/member",
            payload={
                "kind": "user",
                "display_name": "Member",
                "issuer": _ISSUER,
                "subject": "member-sub",
                "email": "member@example.test",
                "active": True,
            },
        )
        assert created["id"] == "member"
        transport.request("PUT", "/v1/admin/security/groups/team", payload={"name": "Team"})
        transport.request("PUT", "/v1/admin/security/groups/team/members/member")
        transport.request("PUT", "/v1/admin/security/role-bindings/group/team/editor")

        assert identities.groups_for_principal(PrincipalId("member")) == (GroupId("team"),)
        assert identities.roles_for_actor(_WS, PrincipalId("member")) == ("editor",)

        transport.request("DELETE", "/v1/admin/security/role-bindings/group/team/editor")
        transport.request("DELETE", "/v1/admin/security/groups/team/members/member")
        assert identities.groups_for_principal(PrincipalId("member")) == ()
        assert identities.roles_for_actor(_WS, PrincipalId("member")) == ()

        events = audit.list_for_resource(
            _WS,
            resource_kind="workspace_resource",
            resource_ref=f"{_WS}/security:principal:member",
        )
        assert len(events) == 1
        assert events[0].action == "authorize:workspace.admin"
        assert events[0].outcome == "allowed"
        assert events[0].actor.ref == admin.id.value
    finally:
        _close(server, thread)


def test_non_admin_is_denied_before_invalid_body_is_parsed(monkeypatch, tmp_path: Path) -> None:
    server, thread, issue_token, identities, audit = _start_server(
        monkeypatch, tmp_path / "ronin.sqlite3"
    )
    viewer = identities.put_principal(_principal("viewer", "viewer-sub"))
    identities.put_role_binding(RoleBinding(_WS, "principal", viewer.id.value, "viewer"))
    transport = _transport(server, issue_token("viewer-sub"))

    try:
        with pytest.raises(APIError) as denied:
            transport.request(
                "PUT",
                "/v1/admin/security/principals/blocked",
                payload={"unknown": "field"},
            )
        assert denied.value.status_code == 403
        assert denied.value.code == "forbidden"
        assert identities.get_principal(PrincipalId("blocked")) is None
        events = audit.list_for_resource(
            _WS,
            resource_kind="workspace_resource",
            resource_ref=f"{_WS}/security:principal:blocked",
        )
        assert len(events) == 1
        assert events[0].outcome == "denied"
    finally:
        _close(server, thread)


def test_group_admin_revocation_is_immediately_authoritative(monkeypatch, tmp_path: Path) -> None:
    server, thread, issue_token, identities, _audit = _start_server(
        monkeypatch, tmp_path / "ronin.sqlite3"
    )
    operator = identities.put_principal(_principal("group-admin", "group-admin-sub"))
    identities.put_group(Group(GroupId("admins"), "Admins"))
    identities.add_group_member(GroupId("admins"), operator.id)
    identities.put_role_binding(RoleBinding(_WS, "group", "admins", "admin"))
    transport = _transport(server, issue_token("group-admin-sub"))

    try:
        transport.request("PUT", "/v1/admin/security/groups/first", payload={"name": "First"})
        assert identities.remove_group_member(GroupId("admins"), operator.id)
        with pytest.raises(APIError) as denied:
            transport.request("PUT", "/v1/admin/security/groups/second", payload={"name": "Second"})
        assert denied.value.status_code == 403
        assert denied.value.code == "forbidden"
    finally:
        _close(server, thread)


def test_admin_errors_are_stable_and_identity_rebinding_conflicts(monkeypatch, tmp_path: Path) -> None:
    server, thread, issue_token, identities, _audit = _start_server(
        monkeypatch, tmp_path / "ronin.sqlite3"
    )
    admin = identities.put_principal(_principal("admin", "admin-sub"))
    identities.put_role_binding(RoleBinding(_WS, "principal", admin.id.value, "admin"))
    transport = _transport(server, issue_token("admin-sub"))

    try:
        transport.request(
            "PUT",
            "/v1/admin/security/principals/member",
            payload={"kind": "user", "display_name": "Member", "issuer": _ISSUER, "subject": "member-sub"},
        )
        with pytest.raises(APIError) as conflict:
            transport.request(
                "PUT",
                "/v1/admin/security/principals/member",
                payload={"kind": "user", "display_name": "Member", "issuer": _ISSUER, "subject": "other-sub"},
            )
        assert conflict.value.status_code == 409
        assert conflict.value.code == "identity_conflict"

        with pytest.raises(APIError) as missing:
            transport.request("PUT", "/v1/admin/security/role-bindings/principal/missing/viewer")
        assert missing.value.status_code == 404
        assert missing.value.code == "subject_not_found"

        with pytest.raises(APIError) as method:
            transport.request("GET", "/v1/admin/security/groups/team")
        assert method.value.status_code == 405
        assert method.value.code == "method_not_allowed"
    finally:
        _close(server, thread)


def test_audit_failure_blocks_admin_mutation(monkeypatch, tmp_path: Path) -> None:
    database = tmp_path / "ronin.sqlite3"
    server, thread, issue_token, identities, _audit = _start_server(
        monkeypatch, database, audit_store=_FailingAuditStore()
    )
    admin = identities.put_principal(_principal("admin", "admin-sub"))
    identities.put_role_binding(RoleBinding(_WS, "principal", admin.id.value, "admin"))
    transport = _transport(server, issue_token("admin-sub"))

    try:
        with pytest.raises(APIError) as failed:
            transport.request("PUT", "/v1/admin/security/groups/blocked", payload={"name": "Blocked"})
        assert failed.value.status_code == 503
        assert failed.value.code == "authorization_audit_unavailable"
        assert identities.groups_for_principal(admin.id) == ()
        with pytest.raises(sqlite3.OperationalError):
            sqlite3.connect(database).execute(
                "SELECT group_id FROM security_groups WHERE group_id='blocked'"
            ).fetchone()
    finally:
        _close(server, thread)


def test_admin_profile_preserves_oidc_job_routes(monkeypatch, tmp_path: Path) -> None:
    server, thread, issue_token, identities, _audit = _start_server(
        monkeypatch, tmp_path / "ronin.sqlite3"
    )
    admin = identities.put_principal(_principal("admin", "admin-sub"))
    identities.put_role_binding(RoleBinding(_WS, "principal", admin.id.value, "admin"))
    client = Ronin(transport=_transport(server, issue_token("admin-sub")))

    try:
        handle = client.submit(
            project=str(_PROJECT),
            target="notebooks/etl",
            idempotency_key="admin-job-1",
        )
        assert client.get_job(handle.id).id == handle.id
    finally:
        _close(server, thread)
