from __future__ import annotations

import asyncio
import urllib.error
import urllib.request
from threading import Thread

import pytest
from studio_core import Grant, GrantSet, ResourceScope
from studio_execution import DurableExecutionService
from studio_orchestrator import Instant
from studio_server import RoninHTTPServer
from studio_storage import SqliteJobStore

_GRANTS = GrantSet(
    (
        Grant(
            frozenset({"read", "list", "events", "submit", "execute", "cancel", "evidence:read"}),
            ResourceScope("*", None),
        ),
    )
)


def test_studio_assets_are_allowlisted_and_served(tmp_path) -> None:
    service = DurableExecutionService(
        SqliteJobStore(tmp_path / "ronin.db", migration_now=Instant("2026-09-06T20:00:00.000000Z"))
    )
    server = RoninHTTPServer(  # noqa: S106
        ("127.0.0.1", 0),
        service,
        token="test-token",  # noqa: S106 - deterministic fixture credential
        grants=_GRANTS,  # noqa: S106
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        with urllib.request.urlopen(  # noqa: S310
            f"{base_url}/studio/", timeout=2
        ) as response:
            assert response.status == 200
            assert response.headers["Content-Type"].startswith("text/html")
            assert b"Ronin Studio" in response.read()
        with urllib.request.urlopen(  # noqa: S310
            f"{base_url}/studio/studio.js", timeout=2
        ) as response:
            assert response.status == 200
            assert response.headers["Content-Type"].startswith("text/javascript")
            script = response.read().decode()
            assert 'method: "POST"' in script
            assert "/cancel" in script
            assert 'classList.toggle("active"' in script
            assert "sessionStorage" in script
            assert "run-project" in script
            assert "run-state" in script
            assert "run-filter-summary" in script
            assert "all projects" in script
            assert "clear-filters" in script
            assert "URLSearchParams" in script
            assert 'params.set("cursor"' in script
            assert 'localStorage.setItem("ronin.token"' not in script
            request = urllib.request.Request(  # noqa: S310
                f"{base_url}/studio/secret.txt",
                headers={"Authorization": "Bearer test-token"},
            )
        with pytest.raises(urllib.error.HTTPError) as error_info:
            urllib.request.urlopen(request, timeout=2)  # noqa: S310
        assert error_info.value.code == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        asyncio.run(service.aclose())
