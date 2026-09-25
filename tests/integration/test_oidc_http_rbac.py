from __future__ import annotations

import json
import time
import urllib.request
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
    OidcConfig,
    OidcTokenValidator,
    Principal,
    PrincipalId,
    RoleBinding,
    SqliteIdentityStore,
)
from studio_server import OidcRoninHTTPServer
from studio_storage import SqliteJobStore, SqliteWorkspaceStore
from studio_storage.audit import SqliteAuditStore

_NOW = Instant("2026-09-13T17:00:00.000000Z")
_WS = WorkspaceId("workspace-oidc")
_PROJECT = ProjectId("project-oidc")
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
    project = Project(
        _PROJECT,
        "OIDC project",
        (
            RepositoryBinding(
                "code",
                "https://git.example.test/team/oidc.git",
                role="primary",
            ),
        ),
        ExecutionProfile(runtime=RuntimeProfileRef("python", "3.11")),
    )
    return ProjectManifest.from_project(project)


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
            {
                "iss": _ISSUER,
                "sub": subject,
                "aud": _AUDIENCE,
                "iat": now,
                "exp": now + 300,
            },
            private_key,
            algorithm="RS256",
            headers={"kid": "key-1"},
        )

    return validator, token


def _stores(database: Path):
    workspaces = SqliteWorkspaceStore(database, migration_now=_NOW)
    workspaces.create_workspace(Workspace(_WS, "OIDC Workspace"), now=_NOW)
    workspaces.register_project(_WS, _manifest(), now=_NOW)
    identities = SqliteIdentityStore(database)
    audit = SqliteAuditStore(database, migration_now=_NOW)
    jobs = SqliteJobStore(database, migration_now=_NOW)
    return workspaces, identities, audit, jobs


def _start_server(monkeypatch, database: Path, *, audit_store=None):
    monkeypatch.setenv("RONIN_DB", str(database))
    validator, token = _oidc_material()
    workspaces, identities, audit, jobs = _stores(database)
    service = DurableExecutionService(jobs)
    server = OidcRoninHTTPServer(
        ("127.0.0.1", 0),
        service,
        workspace_id=_WS,
        validator=validator,
        principal_store=identities,
        rbac_store=identities,
        workspace_store=workspaces,
        audit_store=audit if audit_store is None else audit_store,
    )
    thread = Thread(target=server.serve_forever, name="ronin-oidc-http-test", daemon=True)
    thread.start()
    return server, thread, token, identities, audit


def _client(server: OidcRoninHTTPServer, token: str) -> Ronin:
    transport = HTTPTransport(
        f"http://127.0.0.1:{server.server_port}",
        token=token,
        allow_insecure_localhost=True,
        max_retries=0,
    )
    return Ronin(transport=transport)


def test_oidc_editor_executes_registered_project_and_audits(monkeypatch, tmp_path: Path) -> None:
    database = tmp_path / "ronin.sqlite3"
    server, thread, issue_token, identities, audit = _start_server(monkeypatch, database)
    editor = identities.put_principal(_principal("editor", "editor-sub"))
    identities.put_role_binding(RoleBinding(_WS, "principal", editor.id.value, "editor"))
    token = issue_token("editor-sub")
    client = _client(server, token)

    try:
        job = client.submit(
            project=str(_PROJECT),
            target="notebooks/etl",
            parameters={"limit": 1},
            idempotency_key="oidc-editor-1",
        )
        assert job.id
        page = client.list_jobs(project=str(_PROJECT), limit=10)
        assert [item.id for item in page.items] == [job.id]
        assert client.get_job(job.id).id == job.id
        cancelled = job.cancel()
        assert cancelled.id == job.id

        events = audit.list_for_resource(
            _WS,
            resource_kind="workspace_resource",
            resource_ref=f"{_WS}/project:{_PROJECT}",
        )
        assert events
        assert all(event.actor.ref == editor.id.value for event in events)
        assert {event.action for event in events}.issuperset(
            {"authorize:job.submit", "authorize:job.read", "authorize:job.cancel"}
        )
        assert all(event.outcome == "allowed" for event in events)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5.0)
        assert not thread.is_alive()


def test_oidc_viewer_denial_is_audited_and_unfiltered_list_is_rejected(
    monkeypatch, tmp_path: Path
) -> None:
    database = tmp_path / "ronin.sqlite3"
    server, thread, issue_token, identities, audit = _start_server(monkeypatch, database)
    viewer = identities.put_principal(_principal("viewer", "viewer-sub"))
    identities.put_role_binding(RoleBinding(_WS, "principal", viewer.id.value, "viewer"))
    token = issue_token("viewer-sub")
    transport = HTTPTransport(
        f"http://127.0.0.1:{server.server_port}",
        token=token,
        allow_insecure_localhost=True,
        max_retries=0,
    )

    try:
        with pytest.raises(APIError) as unfiltered:
            transport.request("GET", "/v1/jobs")
        assert unfiltered.value.status_code == 400
        assert unfiltered.value.code == "project_required"

        with pytest.raises(APIError) as denied:
            transport.request(
                "POST",
                "/v1/jobs",
                payload={"project": str(_PROJECT), "target": "notebooks/etl"},
            )
        assert denied.value.status_code == 403
        assert denied.value.code == "forbidden"

        events = audit.list_for_resource(
            _WS,
            resource_kind="workspace_resource",
            resource_ref=f"{_WS}/project:{_PROJECT}",
        )
        submit_events = [event for event in events if event.action == "authorize:job.submit"]
        assert len(submit_events) == 1
        assert submit_events[0].actor.ref == viewer.id.value
        assert submit_events[0].outcome == "denied"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5.0)


def test_oidc_job_visibility_hides_denied_project_job(monkeypatch, tmp_path: Path) -> None:
    database = tmp_path / "ronin.sqlite3"
    server, thread, issue_token, identities, _audit = _start_server(monkeypatch, database)
    editor = identities.put_principal(_principal("editor", "editor-sub"))
    identities.put_role_binding(RoleBinding(_WS, "principal", editor.id.value, "editor"))
    outsider = identities.put_principal(_principal("outsider", "outsider-sub"))

    try:
        created = _client(server, issue_token("editor-sub")).submit(
            project=str(_PROJECT),
            target="notebooks/etl",
            idempotency_key="oidc-hidden-1",
        )
        with pytest.raises(APIError) as hidden:
            _client(server, issue_token("outsider-sub")).get_job(created.id)
        assert hidden.value.status_code == 404
        assert hidden.value.code == "job_not_found"
        assert outsider.id.value == "outsider"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5.0)


def test_oidc_audit_failure_blocks_mutation(monkeypatch, tmp_path: Path) -> None:
    database = tmp_path / "ronin.sqlite3"
    server, thread, issue_token, identities, _audit = _start_server(
        monkeypatch,
        database,
        audit_store=_FailingAuditStore(),
    )
    editor = identities.put_principal(_principal("editor", "editor-sub"))
    identities.put_role_binding(RoleBinding(_WS, "principal", editor.id.value, "editor"))
    transport = HTTPTransport(
        f"http://127.0.0.1:{server.server_port}",
        token=issue_token("editor-sub"),
        allow_insecure_localhost=True,
        max_retries=0,
    )

    try:
        with pytest.raises(APIError) as failed:
            transport.request(
                "POST",
                "/v1/jobs",
                payload={"project": str(_PROJECT), "target": "notebooks/etl"},
            )
        assert failed.value.status_code == 503
        assert failed.value.code == "authorization_audit_unavailable"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5.0)


def test_oidc_unprovisioned_subject_is_401_and_healthz_is_public(
    monkeypatch, tmp_path: Path
) -> None:
    database = tmp_path / "ronin.sqlite3"
    server, thread, issue_token, _identities, _audit = _start_server(monkeypatch, database)
    base_url = f"http://127.0.0.1:{server.server_port}"

    try:
        with urllib.request.urlopen(  # noqa: S310 - loopback test server only
            f"{base_url}/healthz", timeout=2.0
        ) as response:
            assert response.status == 200
            assert json.loads(response.read()) == {"status": "ready"}

        transport = HTTPTransport(
            base_url,
            token=issue_token("missing-sub"),
            allow_insecure_localhost=True,
            max_retries=0,
        )
        with pytest.raises(APIError) as unauthorized:
            transport.request("GET", "/v1/jobs", query={"project": str(_PROJECT)})
        assert unauthorized.value.status_code == 401
        assert unauthorized.value.code == "unauthorized"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5.0)
