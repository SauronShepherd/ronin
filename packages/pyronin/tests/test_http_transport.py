from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from pyronin import APIError, HTTPTransport, TransportError


class _Handler(BaseHTTPRequestHandler):
    seen_authorization: str | None = None

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def do_GET(self) -> None:  # noqa: N802
        type(self).seen_authorization = self.headers.get("Authorization")
        if self.path == "/ok":
            body = json.dumps({"ok": True}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/large":
            body = b'"' + b"x" * 128 + b'"'
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/error":
            body = b"server-secret-token"
            self.send_response(400)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/large-error":
            body = b"server-secret-token" * 16
            self.send_response(500)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/ok")
            self.end_headers()
            return
        self.send_response(404)
        self.end_headers()


@contextmanager
def _server() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_authenticated_plaintext_is_rejected_before_request() -> None:
    with pytest.raises(ValueError, match="requires HTTPS"):
        HTTPTransport("http://example.test", token="synthetic-token")  # noqa: S106


def test_explicit_loopback_development_opt_in_is_narrow() -> None:
    with _server() as base_url:
        transport = HTTPTransport(
            base_url,
            token="synthetic-token",  # noqa: S106
            allow_insecure_localhost=True,
        )
        assert transport.request("GET", "/ok") == {"ok": True}
        assert _Handler.seen_authorization == "Bearer synthetic-token"
    with pytest.raises(ValueError, match="requires HTTPS"):
        HTTPTransport(
            "http://example.test",
            token="synthetic-token",  # noqa: S106
            allow_insecure_localhost=True,
        )


def test_redirects_are_not_followed_by_transport() -> None:
    with _server() as base_url:
        transport = HTTPTransport(base_url)
        with pytest.raises(APIError) as error:
            transport.request("GET", "/redirect")
    assert error.value.status_code == 302
    assert error.value.message == "request failed"


def test_success_and_error_bodies_are_bounded_and_server_text_is_not_surfaced() -> None:
    with _server() as base_url:
        transport = HTTPTransport(base_url, max_response_bytes=32)
        with pytest.raises(TransportError, match="byte limit"):
            transport.request("GET", "/large")
        with pytest.raises(APIError) as ordinary_error:
            transport.request("GET", "/error")
        with pytest.raises(APIError) as large_error:
            transport.request("GET", "/large-error")
    assert ordinary_error.value.status_code == 400
    assert ordinary_error.value.message == "request failed"
    assert "server-secret-token" not in str(ordinary_error.value)
    assert large_error.value.status_code == 500
    assert large_error.value.message == "error response exceeded configured byte limit"
    assert "server-secret-token" not in str(large_error.value)


def test_transport_validates_origin_relative_paths_and_limits() -> None:
    transport = HTTPTransport("https://example.test")
    with pytest.raises(ValueError, match="origin-relative"):
        transport.request("GET", "https://attacker.test/path")
    with pytest.raises(ValueError, match="origin-relative"):
        transport.request("GET", "//attacker.test/path")
    with pytest.raises(ValueError, match="max_response_bytes"):
        HTTPTransport("https://example.test", max_response_bytes=0)
    with pytest.raises(ValueError, match="credentials"):
        HTTPTransport("https://user:pass@example.test")
    with pytest.raises(ValueError, match="query or fragment"):
        HTTPTransport("https://example.test?x=1")
