from __future__ import annotations

from pathlib import Path
from threading import Thread

import pytest
from pyronin import APIError, HTTPTransport
from studio_core.grants import Grant, GrantSet, ResourceScope
from studio_execution import DurableExecutionService
from studio_orchestrator import Instant
from studio_server import RoninHTTPServer
from studio_storage import SqliteJobStore

_MIGRATION_NOW = Instant("2026-09-13T00:00:00.000000Z")
_TOKEN = "pagination-test-token"  # noqa: S105 - deterministic fixture credential


def _server(tmp_path: Path, grants: GrantSet) -> tuple[RoninHTTPServer, Thread]:
    store = SqliteJobStore(tmp_path / "ronin.db", migration_now=_MIGRATION_NOW)
    service = DurableExecutionService(store)
    server = RoninHTTPServer(
        ("127.0.0.1", 0),
        service,
        token=_TOKEN,
        grants=grants,
    )
    thread = Thread(target=server.serve_forever, name="ronin-pagination-auth", daemon=True)
    thread.start()
    return server, thread


def _transport(server: RoninHTTPServer) -> HTTPTransport:
    return HTTPTransport(
        f"http://127.0.0.1:{server.server_port}",
        token=_TOKEN,
        allow_insecure_localhost=True,
        max_retries=0,
    )


def _close(server: RoninHTTPServer, thread: Thread) -> None:
    server.shutdown()
    server.server_close()
    thread.join(timeout=5.0)
    assert not thread.is_alive()


def test_project_scoped_listing_requires_project_before_pagination(tmp_path: Path) -> None:
    grants = GrantSet((Grant(frozenset({"list"}), ResourceScope("project", "allowed")),))
    server, thread = _server(tmp_path, grants)
    try:
        transport = _transport(server)
        with pytest.raises(APIError) as denied:
            transport.request("GET", "/v1/jobs", query={"limit": "1"})
        assert denied.value.status_code == 403
        assert denied.value.code == "forbidden"

        page = transport.request(
            "GET",
            "/v1/jobs",
            query={"project": "allowed", "limit": "1"},
        )
        assert page == {"items": [], "next_cursor": None}
    finally:
        _close(server, thread)


def test_unconstrained_project_wildcard_can_list_without_project(tmp_path: Path) -> None:
    grants = GrantSet((Grant(frozenset({"list"}), ResourceScope("project", None)),))
    server, thread = _server(tmp_path, grants)
    try:
        page = _transport(server).request("GET", "/v1/jobs", query={"limit": "1"})
        assert page == {"items": [], "next_cursor": None}
    finally:
        _close(server, thread)


def test_constrained_wildcard_does_not_enable_unfiltered_listing(tmp_path: Path) -> None:
    grants = GrantSet(
        (
            Grant(
                frozenset({"list"}),
                ResourceScope("project", None),
                (("environment", "prod"),),
            ),
        )
    )
    server, thread = _server(tmp_path, grants)
    try:
        with pytest.raises(APIError) as denied:
            _transport(server).request("GET", "/v1/jobs")
        assert denied.value.status_code == 403
        assert denied.value.code == "forbidden"
    finally:
        _close(server, thread)
