"""Real control-plane journey for the bounded HTTP JSON connector."""

from __future__ import annotations

import http.client
import json
import socket
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from studio_cli.local_composed import build_local_composed_from_env
from studio_core import ConnectionDefinition, ConnectionId


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


@contextmanager
def _real_http_json_service() -> Iterator[tuple[str, list[str]]]:
    requests: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            requests.append(self.path)
            page = parse_qs(urlsplit(self.path).query).get("page", ["1"])[0]
            rows = (
                [{"id": 1, "name": "Ada"}]
                if page == "1"
                else [{"id": 2, "name": "Grace"}]
                if page == "2"
                else []
            )
            body = json.dumps(rows, separators=(",", ":")).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            del format, args

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
    )
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}", requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _request(
    address: tuple[str, int], method: str, path: str, body: object | None = None
) -> tuple[int, dict[str, Any]]:
    connection = http.client.HTTPConnection(*address, timeout=10)
    try:
        encoded = None if body is None else json.dumps(body, separators=(",", ":")).encode("utf-8")
        headers = {"Authorization": "Bearer control-token"}
        if encoded is not None:
            headers["Content-Type"] = "application/json"
        connection.request(method, path, body=encoded, headers=headers)
        response = connection.getresponse()
        return response.status, json.loads(response.read().decode("utf-8"))
    finally:
        connection.close()


def test_control_plane_preview_reads_real_paginated_http_json_service(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setenv("RONIN_DB", str(tmp_path / "ronin.sqlite3"))
    monkeypatch.setenv("RONIN_WORKSPACE_ID", "workspace-1")
    monkeypatch.setenv("RONIN_CONTROL_PLANE_TOKEN", "control-token")
    monkeypatch.setenv(
        "RONIN_CONTROL_PLANE_PERMISSIONS",
        "scheduler.read,scheduler.write,workspace.read,workspace.write,project.read,project.write",
    )
    monkeypatch.setenv(
        "RONIN_TOKEN_SCOPES",
        (
            '{"version":1,"grants":[{"actions":["cancel","evidence:read",'
            '"execute","events","list","read","submit"],"constraints":{},'
            '"resource":{"identifier":null,"kind":"*"},"version":1}]}'
        ),
    )
    monkeypatch.setenv("RONIN_TOKEN", "job-token")
    monkeypatch.setenv("RONIN_PLUGIN_API", "legacy")
    monkeypatch.setenv("RONIN_PORT", str(_free_port()))
    monkeypatch.setenv("RONIN_CONTROL_PLANE_PORT", str(_free_port()))

    with _real_http_json_service() as (origin, requests):
        composition = build_local_composed_from_env()
        try:
            composition.start()
            address = composition.control_plane_server.server_address
            connection = ConnectionDefinition(
                ConnectionId("conn-http-real"),
                "Real HTTP JSON source",
                "http.json",
                options=(
                    ("allow_http", "true"),
                    ("allow_private_network", "true"),
                    ("base_url", f"{origin}/api"),
                    ("max_pages", "3"),
                    ("page_param", "page"),
                    ("page_size", "1"),
                    ("timeout_seconds", "2"),
                ),
            )
            create_status, created = _request(
                address,
                "POST",
                "/v1/workspaces/workspace-1/connections",
                connection.to_payload(),
            )
            preview_status, preview = _request(
                address,
                "POST",
                "/v1/platform/connectors/preview?workspace_id=workspace-1",
                {
                    "id": "http-preview",
                    "connector_id": "http.json",
                    "connection_ref": "conn-http-real",
                    "asset_ref": "conn-http-real::v1.records",
                    "destination_ref": "local/http-preview",
                    "checkpoint_identity": "http-preview-v1",
                    "mode": "snapshot",
                },
            )
        finally:
            composition.stop()

    assert create_status == 201
    assert created["id"] == "conn-http-real"
    assert preview_status == 200
    assert preview["schema"] == "ronin.ingestion-preview/v1"
    assert preview["row_count"] == 2
    assert preview["rows"] == [
        {"id": 1, "name": "Ada"},
        {"id": 2, "name": "Grace"},
    ]
    assert preview["checkpoint"]["present"] is False
    assert requests == [
        "/api/v1/records?page=1",
        "/api/v1/records?page=2",
        "/api/v1/records?page=3",
    ]
