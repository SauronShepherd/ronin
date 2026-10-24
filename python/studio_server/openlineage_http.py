"""HTTP delivery adapter for the provider-neutral OpenLineage transport."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Callable, Mapping
from contextlib import closing
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from studio_core import OpenLineageTransportError, validate_openlineage_event
from studio_core.canonical_json import encode as encode_canonical_json
from studio_core.openlineage import JsonValue


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, *_args: object, **_kwargs: object) -> None:
        return None


def _open_without_redirects(request: Request, timeout: float) -> object:
    return build_opener(_RejectRedirects()).open(request, timeout=timeout)


class HttpOpenLineageSink:
    """Secure, bounded HTTP sink; transport retries remain in the core wrapper."""

    def __init__(
        self,
        endpoint: str,
        *,
        timeout_seconds: float = 5.0,
        opener: Callable[..., object] | None = None,
    ):
        try:
            if not isinstance(endpoint, str):
                raise ValueError("OpenLineage endpoint must use a valid HTTP(S) URL")
            parsed = urlsplit(endpoint)
            hostname = parsed.hostname
            port = parsed.port
        except ValueError as exc:
            raise ValueError("OpenLineage endpoint must use a valid HTTP(S) URL") from exc
        if (
            parsed.scheme not in {"https", "http"}
            or not parsed.netloc
            or not hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
        ):
            raise ValueError(
                "OpenLineage endpoint must be an absolute HTTP(S) URL "
                "without credentials or fragment"
            )
        if port is not None and not 1 <= port <= 65535:
            raise ValueError("OpenLineage endpoint port must be between 1 and 65535")
        if parsed.scheme == "http" and hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("OpenLineage HTTP endpoints must use HTTPS outside localhost")
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not _is_finite_timeout(timeout_seconds)
            or timeout_seconds <= 0
            or timeout_seconds > 60
        ):
            raise ValueError("OpenLineage timeout must be between 0 and 60 seconds")
        self._endpoint = endpoint
        self._timeout_seconds = timeout_seconds
        self._opener = opener or _open_without_redirects

    def publish(self, event: Mapping[str, JsonValue]) -> None:
        validate_openlineage_event(event)
        body = encode_canonical_json(dict(event))
        event_digest = hashlib.sha256(body).hexdigest()
        request = Request(  # noqa: S310 - endpoint scheme was validated above
            self._endpoint,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "X-Ronin-Event-Digest": event_digest,
            },
        )
        try:
            response = self._opener(request, timeout=self._timeout_seconds)
            with closing(cast(Any, response)):
                status = int(getattr(response, "status", 200))
        except (HTTPError, URLError, OSError) as exc:
            if isinstance(exc, HTTPError):
                exc.close()
            raise OpenLineageTransportError("OpenLineage endpoint request failed") from exc
        except OpenLineageTransportError:
            raise
        except Exception as exc:  # noqa: BLE001 - normalize provider/network details
            raise OpenLineageTransportError("OpenLineage endpoint request failed") from exc
        if not 200 <= status < 300:
            raise OpenLineageTransportError("OpenLineage endpoint returned a non-success status")


__all__ = ("HttpOpenLineageSink",)


def _is_finite_timeout(value: int | float) -> bool:
    try:
        return math.isfinite(value)
    except OverflowError:
        return False
