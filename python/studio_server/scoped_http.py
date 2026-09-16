"""Secure-default public wrapper for the canonical typed-grant HTTP server."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Coroutine
from concurrent.futures import Future, TimeoutError as FutureTimeoutError
from collections.abc import Callable
from http import HTTPStatus
from pathlib import Path
from typing import Any, cast

from studio_core import GrantSet
from studio_execution import DurableExecutionService
from studio_sql import SqlEngine
from studio_storage import sqlite_ready

from studio_server.http import RoninHTTPServer as _RoninHTTPServer
from studio_server.http import _Handler
from studio_server.transport_policy import (
    BindPolicy,
    allows_plaintext_non_loopback,
    is_loopback_host,
    parse_bind_policy,
)

_BIND_POLICY_ENV = "RONIN_BIND_POLICY"
_REQUEST_TIMEOUT_ENV = "RONIN_HTTP_REQUEST_TIMEOUT_SECONDS"
_SERVICE_TIMEOUT_ENV = "RONIN_HTTP_SERVICE_TIMEOUT_SECONDS"
_DEFAULT_REQUEST_TIMEOUT_SECONDS = 15.0
_DEFAULT_SERVICE_TIMEOUT_SECONDS = 30.0


class ServiceCallTimeout(TimeoutError):
    """Raised when one public HTTP service call exceeds its configured deadline."""


def _positive_timeout_from_env(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive number of seconds") from exc
    if not 0 < value <= 3600:
        raise ValueError(f"{name} must be in (0, 3600]")
    return value


def _bind_policy_from_env() -> BindPolicy:
    return parse_bind_policy(os.environ.get(_BIND_POLICY_ENV))


def _readiness_database_from_env() -> Path:
    return Path(os.environ.get("RONIN_DB", ".ronin/ronin.sqlite3")).expanduser().resolve()


class _BoundedServiceLoop:
    """Apply HTTP endpoint deadlines while preserving the original shutdown lifecycle."""

    def __init__(self, delegate: Any, timeout_seconds: float) -> None:
        self._delegate = delegate
        self._timeout_seconds = timeout_seconds

    def call(self, coroutine: Coroutine[Any, Any, Any]) -> Any:
        future: Future[Any] = asyncio.run_coroutine_threadsafe(coroutine, self._delegate._loop)
        try:
            return future.result(timeout=self._timeout_seconds)
        except FutureTimeoutError as exc:
            future.cancel()
            raise ServiceCallTimeout("HTTP service call exceeded configured deadline") from exc

    def close(self) -> None:
        # Shutdown is lifecycle work, not an endpoint request. Delegate to the original
        # implementation so service.aclose() is not accidentally cut off by the endpoint deadline.
        self._delegate.close()


class _ReadinessHandler(_Handler):
    """Add one non-versioned readiness route and stable timeout responses."""

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/healthz":
            server = cast(RoninHTTPServer, self.server)
            ready = server.ready()
            self._write_json(
                HTTPStatus.OK if ready else HTTPStatus.SERVICE_UNAVAILABLE,
                {"status": "ready" if ready else "not_ready"},
            )
            return
        try:
            super().do_GET()
        except ServiceCallTimeout:
            self._error(
                HTTPStatus.GATEWAY_TIMEOUT,
                "service_timeout",
                "service call exceeded configured deadline",
            )
        except TimeoutError:
            self._error(
                HTTPStatus.REQUEST_TIMEOUT,
                "request_timeout",
                "request exceeded configured deadline",
            )

    def do_POST(self) -> None:  # noqa: N802
        try:
            super().do_POST()
        except ServiceCallTimeout:
            self._error(
                HTTPStatus.GATEWAY_TIMEOUT,
                "service_timeout",
                "service call exceeded configured deadline",
            )
        except TimeoutError:
            self._error(
                HTTPStatus.REQUEST_TIMEOUT,
                "request_timeout",
                "request exceeded configured deadline",
            )


class RoninHTTPServer(_RoninHTTPServer):
    """Supported plaintext server with explicit binding, readiness and deadlines."""

    def __init__(
        self,
        server_address: tuple[str, int],
        service: DurableExecutionService,
        *,
        token: str,
        grants: GrantSet,
        sql_engine: SqlEngine | None = None,
        readiness_probe: Callable[[], bool] | None = None,
    ) -> None:
        host, _port = server_address
        policy = _bind_policy_from_env()
        if not is_loopback_host(host) and not allows_plaintext_non_loopback(policy):
            raise ValueError(
                "Ronin's built-in server is plaintext HTTP; non-loopback binding requires "
                "RONIN_BIND_POLICY=container-internal for the supported private Compose "
                "bridge, or RONIN_BIND_POLICY=insecure-plaintext-network for an explicit "
                "trusted development network. Use an external TLS terminator for remote access."
            )
        self._readiness_database = _readiness_database_from_env()
        self._readiness_probe = readiness_probe
        self._request_timeout_seconds = _positive_timeout_from_env(
            _REQUEST_TIMEOUT_ENV,
            _DEFAULT_REQUEST_TIMEOUT_SECONDS,
        )
        service_timeout_seconds = _positive_timeout_from_env(
            _SERVICE_TIMEOUT_ENV,
            _DEFAULT_SERVICE_TIMEOUT_SECONDS,
        )
        super().__init__(
            server_address,
            service,
            token=token,
            grants=grants,
            sql_engine=sql_engine,
        )
        original_loop = getattr(self.application, "_loop")
        setattr(
            self.application, "_loop", _BoundedServiceLoop(original_loop, service_timeout_seconds)
        )
        self.RequestHandlerClass = _ReadinessHandler

    def get_request(self) -> tuple[Any, Any]:
        request, client_address = super().get_request()
        request.settimeout(self._request_timeout_seconds)
        return request, client_address

    def ready(self) -> bool:
        """Return readiness without exposing storage details through HTTP."""
        if self._readiness_probe is not None:
            return self._readiness_probe()
        return sqlite_ready(self._readiness_database)


__all__ = ("RoninHTTPServer", "ServiceCallTimeout")
