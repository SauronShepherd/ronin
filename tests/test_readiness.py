from __future__ import annotations

import http.server
import importlib.util
import sqlite3
from pathlib import Path
from threading import Thread

from studio_storage import sqlite_ready


def _ready_database(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (3, '2026-09-11T00:00:00Z')"
        )
        connection.execute("CREATE TABLE jobs(job_id TEXT PRIMARY KEY)")
        connection.commit()
    finally:
        connection.close()


def test_sqlite_readiness_requires_current_schema_and_operational_jobs_table(tmp_path: Path) -> None:
    database = tmp_path / "ronin.sqlite3"
    assert not sqlite_ready(database)

    _ready_database(database)
    assert sqlite_ready(database)

    connection = sqlite3.connect(database)
    try:
        connection.execute("DELETE FROM schema_migrations WHERE version = 3")
        connection.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (2, '2026-09-11T00:00:00Z')"
        )
        connection.commit()
    finally:
        connection.close()
    assert not sqlite_ready(database)

    connection = sqlite3.connect(database)
    try:
        connection.execute("DELETE FROM schema_migrations")
        connection.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (3, '2026-09-11T00:00:00Z')"
        )
        connection.execute("DROP TABLE jobs")
        connection.commit()
    finally:
        connection.close()
    assert not sqlite_ready(database)


def _healthcheck_module() -> object:
    path = Path("docker/healthcheck.py")
    spec = importlib.util.spec_from_file_location("ronin_container_healthcheck", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _serve_once(status: int, body: bytes, content_type: str = "application/json") -> tuple[http.server.HTTPServer, Thread]:
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, _format: str, *args: object) -> None:
            del args

        def do_GET(self) -> None:  # noqa: N802
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.handle_request, daemon=True)
    thread.start()
    return server, thread


def test_container_healthcheck_requires_exact_ready_response(monkeypatch) -> None:
    module = _healthcheck_module()

    for status, body, content_type, expected in (
        (200, b'{"status":"ready"}', "application/json", 0),
        (503, b'{"status":"not_ready"}', "application/json", 1),
        (200, b'{"status":"not_ready"}', "application/json", 1),
        (200, b'{"status":"ready"}', "text/plain", 1),
    ):
        server, thread = _serve_once(status, body, content_type)
        monkeypatch.setenv("RONIN_HEALTH_HOST", "127.0.0.1")
        monkeypatch.setenv("RONIN_PORT", str(server.server_port))
        try:
            assert module.main() == expected
        finally:
            thread.join(timeout=2)
            server.server_close()


def test_container_healthcheck_rejects_invalid_configuration(monkeypatch) -> None:
    module = _healthcheck_module()
    monkeypatch.setenv("RONIN_PORT", "not-a-port")
    assert module.main() == 2

    monkeypatch.setenv("RONIN_PORT", "70000")
    assert module.main() == 2

    monkeypatch.setenv("RONIN_PORT", "8080")
    monkeypatch.setenv("RONIN_HEALTH_HOST", " bad-host ")
    assert module.main() == 2
