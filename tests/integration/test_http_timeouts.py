from __future__ import annotations

import asyncio
import socket
from pathlib import Path
from threading import Event, Thread

import pytest
from studio_core.grants import Grant, GrantSet, ResourceScope
from studio_execution import DurableExecutionService
from studio_orchestrator import Instant
from studio_server import RoninHTTPServer
from studio_server.scoped_http import ServiceCallTimeout, _BoundedServiceLoop
from studio_storage import SqliteJobStore

_MIGRATION_NOW = Instant("2026-09-13T00:00:00.000000Z")
_TOKEN = "timeout-test-token"


def _grants() -> GrantSet:
    return GrantSet(
        (
            Grant(
                frozenset({"list", "submit", "execute"}),
                ResourceScope("project", None),
            ),
        )
    )


def _service(tmp_path: Path) -> DurableExecutionService:
    return DurableExecutionService(
        SqliteJobStore(tmp_path / "ronin.db", migration_now=_MIGRATION_NOW)
    )


def test_slow_request_body_hits_configured_read_deadline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RONIN_HTTP_REQUEST_TIMEOUT_SECONDS", "0.1")
    server = RoninHTTPServer(
        ("127.0.0.1", 0),
        _service(tmp_path),
        token=_TOKEN,
        grants=_grants(),
    )
    thread = Thread(target=server.serve_forever, name="ronin-slow-body", daemon=True)
    thread.start()
    client = socket.create_connection(("127.0.0.1", server.server_port), timeout=2.0)
    client.settimeout(2.0)
    try:
        request = (
            "POST /v1/jobs HTTP/1.1\r\n"
            f"Host: 127.0.0.1:{server.server_port}\r\n"
            f"Authorization: Bearer {_TOKEN}\r\n"
            "Content-Type: application/json\r\n"
            "Content-Length: 128\r\n"
            "Connection: close\r\n"
            "\r\n"
        ).encode("ascii")
        client.sendall(request)
        response = b""
        while b"request_timeout" not in response:
            chunk = client.recv(4096)
            if not chunk:
                break
            response += chunk
        assert b" 408 " in response
        assert b"request_timeout" in response
    finally:
        client.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5.0)
        assert not thread.is_alive()


class _LoopDelegate:
    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = Thread(target=self._run, name="ronin-timeout-loop", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def close(self) -> None:
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5.0)
        assert not self._thread.is_alive()
        self._loop.close()


def test_service_deadline_cancels_submitted_future() -> None:
    delegate = _LoopDelegate()
    bounded = _BoundedServiceLoop(delegate, 0.05)
    cancelled = Event()

    async def blocked() -> None:
        try:
            await asyncio.sleep(60)
        finally:
            cancelled.set()

    try:
        with pytest.raises(ServiceCallTimeout):
            bounded.call(blocked())
        assert cancelled.wait(timeout=1.0)
    finally:
        bounded.close()


def test_service_call_below_deadline_succeeds() -> None:
    delegate = _LoopDelegate()
    bounded = _BoundedServiceLoop(delegate, 1.0)

    async def immediate() -> str:
        await asyncio.sleep(0)
        return "ok"

    try:
        assert bounded.call(immediate()) == "ok"
    finally:
        bounded.close()


def test_invalid_timeout_configuration_fails_server_construction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RONIN_HTTP_SERVICE_TIMEOUT_SECONDS", "0")
    service = _service(tmp_path)
    with pytest.raises(ValueError, match="RONIN_HTTP_SERVICE_TIMEOUT_SECONDS"):
        RoninHTTPServer(
            ("127.0.0.1", 0),
            service,
            token=_TOKEN,
            grants=_grants(),
        )
    asyncio.run(service.aclose())
