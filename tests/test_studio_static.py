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
            assert b"RONIN Studio" in response.read()
            assert response.headers["Cache-Control"] == "no-cache"
        for asset, content_type in (("js/app.js", "text/javascript"), ("styles/base.css", "text/css"), ("assets/ronin-logo-full.png", "image/png")):
            with urllib.request.urlopen(f"{base_url}/studio/{asset}", timeout=2) as response:  # noqa: S310
                assert response.status == 200
                assert response.headers["Content-Type"].startswith(content_type)
        with pytest.raises(urllib.error.HTTPError) as error_info:
            urllib.request.urlopen(f"{base_url}/studio/../pyproject.toml", timeout=2)  # noqa: S310
        assert error_info.value.code == 404
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
