"""HTTP delivery adapter for the provider-neutral OpenLineage transport."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from studio_core import OpenLineageTransportError
from studio_core.canonical_json import encode as encode_canonical_json
from studio_core.openlineage import JsonValue


class HttpOpenLineageSink:
    """Secure, bounded HTTP sink; transport retries remain in the core wrapper."""

    def __init__(
        self,
        endpoint: str,
        *,
        timeout_seconds: float = 5.0,
        opener: Callable[..., object] = urlopen,
    ):
        parsed = urlsplit(endpoint)
        if parsed.scheme not in {"https", "http"} or not parsed.netloc:
            raise ValueError("OpenLineage endpoint must be an absolute HTTP(S) URL")
        if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("OpenLineage HTTP endpoints must use HTTPS outside localhost")
        if timeout_seconds <= 0 or timeout_seconds > 60:
            raise ValueError("OpenLineage timeout must be between 0 and 60 seconds")
        self._endpoint = endpoint
        self._timeout_seconds = timeout_seconds
        self._opener = opener

    def publish(self, event: Mapping[str, JsonValue]) -> None:
        body = json.dumps(dict(event), sort_keys=True, separators=(",", ":")).encode("utf-8")
        request = Request(  # noqa: S310 - endpoint scheme was validated above
            self._endpoint,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "X-Ronin-Event-Digest": hashlib.sha256(
                    encode_canonical_json(dict(event))
                ).hexdigest(),
            },
        )
        try:
            response = self._opener(request, timeout=self._timeout_seconds)
            if not 200 <= int(getattr(response, "status", 200)) < 300:
                raise OpenLineageTransportError(
                    "OpenLineage endpoint returned a non-success status"
                )
        except OpenLineageTransportError:
            raise
        except Exception as exc:  # noqa: BLE001 - normalize provider/network details
            raise OpenLineageTransportError("OpenLineage endpoint request failed") from exc


__all__ = ("HttpOpenLineageSink",)
