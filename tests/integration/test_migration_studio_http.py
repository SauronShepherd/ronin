from __future__ import annotations

import base64
import json
from io import BytesIO
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from zipfile import ZIP_DEFLATED, ZipFile

from studio_core import Grant, GrantSet, ResourceScope
from studio_execution import DurableExecutionService
from studio_migration import MigrationAPIRouter, MigrationSessionService
from studio_orchestrator import Instant
from studio_server import RoninHTTPServer
from studio_storage import SqliteJobStore


def test_migration_session_routes_work_through_real_http(tmp_path) -> None:
    grants = GrantSet((Grant(frozenset({"read", "list", "submit"}), ResourceScope("*", None)),))
    service = DurableExecutionService(
        SqliteJobStore(
            tmp_path / "jobs.sqlite3", migration_now=Instant("2026-09-19T00:00:00.000000Z")
        )
    )
    router = MigrationAPIRouter(MigrationSessionService())
    server = RoninHTTPServer(
        ("127.0.0.1", 0),
        service,
        token="test-token",  # noqa: S106
        grants=grants,
        migration_router=router,  # noqa: S106
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = (
            f"http://127.0.0.1:{server.server_port}/v1/workspaces/ws/projects/p/migration/sessions"
        )
        request = Request(
            url,
            data=b"{}",
            method="POST",
            headers={"Authorization": "Bearer test-token", "Content-Type": "application/json"},
        )
        with urlopen(request) as response:  # noqa: S310
            body = json.loads(response.read())
        assert body["workspace_id"] == "ws"
        artifact_request = Request(  # noqa: S310
            f"{url}/{body['id']}/source-artifacts/export.zip",
            data=b"binary-fixture",
            method="PUT",
            headers={
                "Authorization": "Bearer test-token",
                "Content-Type": "application/zip",
            },
        )
        with urlopen(artifact_request) as response:  # noqa: S310
            artifact = json.loads(response.read())
        assert artifact["inventory_digest"]
        with urlopen(Request(url, headers={"Authorization": "Bearer test-token"})) as response:  # noqa: S310
            listing = json.loads(response.read())
        assert len(listing["items"]) == 1
    finally:
        server.shutdown()
        server.server_close()


def test_migration_discovery_and_scope_work_through_real_http(tmp_path) -> None:
    grants = GrantSet((Grant(frozenset({"read", "list", "submit"}), ResourceScope("*", None)),))
    service = DurableExecutionService(
        SqliteJobStore(
            tmp_path / "jobs.sqlite3", migration_now=Instant("2026-09-19T00:00:00.000000Z")
        )
    )
    router = MigrationAPIRouter(MigrationSessionService())
    server = RoninHTTPServer(
        ("127.0.0.1", 0),
        service,
        token="test-token",  # noqa: S106
        grants=grants,
        migration_router=router,  # noqa: S106
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        root = f"http://127.0.0.1:{server.server_port}/v1/workspaces/ws/projects/p/migration"
        headers = {"Authorization": "Bearer test-token", "Content-Type": "application/json"}
        with urlopen(  # noqa: S310
            Request(  # noqa: S310
                f"{root}/sessions", data=b"{}", method="POST", headers=headers
            )
        ) as response:
            session = json.loads(response.read())
        archive = BytesIO()
        with ZipFile(archive, "w", ZIP_DEFLATED) as bundle:
            bundle.writestr("mapping.dtemplate.json", json.dumps({"mappingId": "map-1"}))
            bundle.writestr("process.mtt.json", json.dumps({"id": "proc-1", "mappingId": "map-1"}))
        discover = {
            "archives": [
                {
                    "name": "export.zip",
                    "content_base64": base64.b64encode(archive.getvalue()).decode(),
                }
            ]
        }
        with urlopen(  # noqa: S310
            Request(  # noqa: S310
                f"{root}/sessions/{session['id']}/discover",
                data=json.dumps(discover).encode(),
                method="POST",
                headers=headers,
            )
        ) as response:
            discovered = json.loads(response.read())
        assert discovered["state"] == "scope_ready"
        scope = {"selected": ["iics:process:proc-1"]}
        try:
            with urlopen(  # noqa: S310
                Request(  # noqa: S310
                    f"{root}/sessions/{session['id']}/scope",
                    data=json.dumps(scope).encode(),
                    method="PUT",
                    headers=headers,
                )
            ) as response:
                scoped = json.loads(response.read())
        except HTTPError as error:
            raise AssertionError(error.read().decode()) from error
        assert scoped["state"] == "scope_ready"
        assert scoped["scope_digest"]
        with urlopen(  # noqa: S310
            Request(  # noqa: S310
                f"{root}/sessions/{session['id']}/generate",
                data=b"{}",
                method="POST",
                headers=headers,
            )
        ) as response:
            generated = json.loads(response.read())
        assert generated["project_digest"]
        with urlopen(  # noqa: S310
            Request(  # noqa: S310
                f"{root}/sessions/{session['id']}/qualify",
                data=b"{}",
                method="POST",
                headers=headers,
            )
        ) as response:
            qualified = json.loads(response.read())
        assert qualified["status"] == "passed"
    finally:
        server.shutdown()
        server.server_close()
