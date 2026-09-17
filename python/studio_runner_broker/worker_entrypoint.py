"""Compose worker entrypoint that has no direct Docker authority."""

from __future__ import annotations

import asyncio
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from studio_core.canonical_json import decode as decode_canonical_json
from studio_core.transport_policy import allows_plaintext_non_loopback, parse_bind_policy
from studio_orchestrator import Instant
from studio_runners import BrokerExecutorConfig
from studio_worker import BrokerWorkerRuntime, LocalWorkerRuntimeConfig, WorkerPaths

_IMMUTABLE_IMAGE = re.compile(r"^(?:[^\s]+@)?sha256:[0-9a-f]{64}$")


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(
        self, req: Any, fp: Any, code: Any, msg: Any, headers: Any, newurl: Any
    ) -> None:
        del req, fp, code, msg, headers, newurl
        return


def _env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if value is None or not value or value != value.strip():
        raise ValueError(f"{name} must be set to a non-empty trimmed value")
    return value


def _boolean_env(name: str, default: str = "false") -> bool:
    value = _env(name, default).casefold()
    if value not in {"true", "false"}:
        raise ValueError(f"{name} must be true or false")
    return value == "true"


def _now() -> Instant:
    return Instant(datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ"))


def _runtime_image(base_url: str, token: str, *, allow_insecure_http: bool) -> str:
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"http", "https"} or parsed.hostname is None:
        raise ValueError("runner broker URL must be absolute HTTP(S)")
    if (
        parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("runner broker URL must not contain credentials/query/fragment")
    if parsed.path not in {"", "/"}:
        raise ValueError("runner broker URL must not contain a path")
    if parsed.scheme == "http" and not allow_insecure_http:
        raise ValueError("plaintext runner broker HTTP requires explicit opt-in")
    if not token or token != token.strip() or "\n" in token or "\r" in token or "\x00" in token:
        raise ValueError("runner broker token must be non-empty, trimmed, and single-line")
    request = Request(  # noqa: S310
        base_url.rstrip("/") + "/v1/runtime",
        headers={"Accept": "application/json", "Authorization": f"Bearer {token}"},
        method="GET",
    )
    try:
        with build_opener(_RejectRedirects()).open(request, timeout=10.0) as response:  # noqa: S310
            body = response.read(64 * 1024 + 1)
    except (HTTPError, URLError, OSError) as exc:
        raise RuntimeError("runner broker runtime discovery failed") from exc
    if len(body) > 64 * 1024:
        raise RuntimeError("runner broker runtime response exceeded byte limit")
    try:
        payload = decode_canonical_json(body)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("runner broker runtime response is invalid") from exc
    if (
        not isinstance(payload, dict)
        or set(payload) != {"version", "image"}
        or payload.get("version") != 1
    ):
        raise RuntimeError("runner broker runtime response has invalid fields")
    image = payload.get("image")
    if not isinstance(image, str) or not _IMMUTABLE_IMAGE.fullmatch(image):
        raise RuntimeError("runner broker runtime image is invalid")
    return image


def main() -> int:
    try:
        broker_url = _env("RONIN_RUNNER_BROKER_URL")
        broker_token = _env("RONIN_RUNNER_BROKER_TOKEN")
        transport_policy = parse_bind_policy(os.environ.get("RONIN_BIND_POLICY"))
        allow_insecure = allows_plaintext_non_loopback(transport_policy)
        image = _runtime_image(
            broker_url,
            broker_token,
            allow_insecure_http=allow_insecure,
        )
        database = Path(_env("RONIN_DB", ".ronin/ronin.sqlite3")).expanduser().resolve()
        workspace = Path(_env("RONIN_WORKSPACE", ".")).expanduser().resolve()
        config = LocalWorkerRuntimeConfig(
            paths=WorkerPaths(workspace, database.parent),
            owner=_env("RONIN_WORKER_OWNER", f"worker-{os.getpid()}"),
            image=image,
            database_name=database.name,
        )
        broker = BrokerExecutorConfig(
            broker_url,
            broker_token,
            image,
            allow_insecure_http=allow_insecure,
            request_timeout_seconds=config.limits.timeout_seconds + 30.0,
        )
    except (RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    async def run() -> None:
        async with BrokerWorkerRuntime(config, broker, migration_now=_now()) as runtime:
            await runtime.run_until_signalled()

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        return 130
    return 0


__all__ = ("main",)
