"""Thin standard-library client for the supported Ronin v0.1 HTTP job surface."""

from __future__ import annotations

import ipaddress
import json
import os
import re
from dataclasses import dataclass, field
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, OpenerDirector, Request, build_opener

_MAX_RESPONSE_BYTES = 1024 * 1024
_MAX_ERROR_BYTES = 64 * 1024
_MAX_CURSOR_BYTES = 4096
_INSECURE_REMOTE_HTTP_ENV = "RONIN_INSECURE_ALLOW_REMOTE_HTTP"
_INSTANT_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z$")
_JOB_FIELDS = frozenset({"id", "state", "failure_code"})
_EVENT_FIELDS = frozenset(
    {"sequence", "attempt_id", "attempt_sequence", "kind", "message", "occurred_at"}
)
_EVIDENCE_FIELDS = frozenset(
    {
        "version",
        "cell_id",
        "role",
        "digest_algorithm",
        "digest",
        "media_type",
        "size_bytes",
        "availability",
        "reason",
    }
)


class ControlPlaneError(RuntimeError):
    """Expected control-plane transport or protocol failure."""


class _RejectRedirects(HTTPRedirectHandler):
    """Keep an authenticated request on its already-validated origin."""

    def redirect_request(
        self,
        req: Request,
        fp: object,
        code: int,
        msg: str,
        headers: object,
        newurl: str,
    ) -> None:
        del req, fp, code, msg, headers, newurl
        return None


def is_loopback_host(hostname: str | None) -> bool:
    """Return whether a literal URL/server host is an explicit loopback target."""
    if hostname is None:
        return False
    if hostname.casefold() == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def _insecure_remote_http_enabled() -> bool:
    value = os.environ.get(_INSECURE_REMOTE_HTTP_ENV)
    if value is None or value == "0":
        return False
    if value == "1":
        return True
    raise ValueError(f"{_INSECURE_REMOTE_HTTP_ENV} must be 0 or 1 when set")


def _protocol_cursor(value: object, *, name: str, nullable: bool) -> str | None:
    if value is None and nullable:
        return None
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value.encode("utf-8")) > _MAX_CURSOR_BYTES
    ):
        raise ControlPlaneError(f"Ronin {name} violated the protocol")
    return value


def _error_code(payload: object) -> str | None:
    if not isinstance(payload, dict) or set(payload) != {"error"}:
        return None
    error = payload.get("error")
    if not isinstance(error, dict) or set(error) != {"code", "message"}:
        return None
    code = error.get("code")
    message = error.get("message")
    if (
        not isinstance(code, str)
        or not code
        or len(code) > 128
        or not isinstance(message, str)
        or not message
    ):
        return None
    return code


@dataclass(frozen=True, slots=True)
class ControlPlaneClient:
    base_url: str
    token: str
    timeout: float = 30.0
    allow_insecure_remote_http: bool = field(default_factory=_insecure_remote_http_enabled)
    _opener: OpenerDirector = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        parsed = urlsplit(self.base_url)
        if parsed.scheme not in {"http", "https"} or parsed.hostname is None:
            raise ValueError("RONIN_URL must be an absolute http(s) URL")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("RONIN_URL must not contain credentials")
        if parsed.query or parsed.fragment:
            raise ValueError("RONIN_URL must not contain query or fragment")
        if not self.token or self.token != self.token.strip():
            raise ValueError("Ronin token must be non-empty and trimmed")
        if self.timeout <= 0:
            raise ValueError("timeout must be positive")
        if (
            parsed.scheme == "http"
            and not is_loopback_host(parsed.hostname)
            and not self.allow_insecure_remote_http
        ):
            raise ValueError(
                "RONIN_URL requires HTTPS for authenticated non-loopback endpoints; "
                "set RONIN_INSECURE_ALLOW_REMOTE_HTTP=1 only for explicit "
                "local-development networks"
            )
        object.__setattr__(self, "_opener", build_opener(_RejectRedirects()))

    def request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, object] | None = None,
        query: dict[str, str] | None = None,
        idempotency_key: str | None = None,
    ) -> object:
        if not path.startswith("/") or path.startswith("//"):
            raise ValueError("path must be origin-relative")
        url = self.base_url.rstrip("/") + path
        if query:
            url += "?" + urlencode(query)
        headers = {"Accept": "application/json", "Authorization": f"Bearer {self.token}"}
        body = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        if idempotency_key is not None:
            headers["Idempotency-Key"] = idempotency_key
        request = Request(url, data=body, headers=headers, method=method)  # noqa: S310
        try:
            with self._opener.open(request, timeout=self.timeout) as response:  # noqa: S310
                data = response.read(_MAX_RESPONSE_BYTES + 1)
        except HTTPError as exc:
            try:
                error_body = exc.read(_MAX_ERROR_BYTES + 1)
                if len(error_body) > _MAX_ERROR_BYTES:
                    parsed_error = None
                else:
                    parsed_error = json.loads(error_body) if error_body else None
            except (OSError, json.JSONDecodeError, UnicodeDecodeError):
                parsed_error = None
            code = _error_code(parsed_error)
            suffix = f" [{code}]" if code else ""
            raise ControlPlaneError(f"Ronin API error {exc.code}{suffix}") from exc
        except URLError as exc:
            raise ControlPlaneError("Ronin endpoint unavailable") from exc
        if len(data) > _MAX_RESPONSE_BYTES:
            raise ControlPlaneError("Ronin response exceeded configured byte limit")
        if not data:
            return None
        try:
            return json.loads(data)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ControlPlaneError("Ronin endpoint returned invalid JSON") from exc

    def submit(
        self,
        *,
        project: str,
        target: str,
        parameters: dict[str, object],
        idempotency_key: str | None,
    ) -> dict[str, object]:
        return _job(
            self.request(
                "POST",
                "/v1/jobs",
                payload={"project": project, "target": target, "parameters": parameters},
                idempotency_key=idempotency_key,
            )
        )

    def status(self, job_id: str) -> dict[str, object]:
        return _job(self.request("GET", f"/v1/jobs/{quote(job_id, safe='')}"))

    def jobs(
        self,
        *,
        project: str | None,
        state: str | None,
        limit: int,
        cursor: str | None,
    ) -> dict[str, object]:
        query = {"limit": str(limit)}
        if project is not None:
            query["project"] = project
        if state is not None:
            query["state"] = state
        if cursor is not None:
            query["cursor"] = cursor
        payload = self.request("GET", "/v1/jobs", query=query)
        if not isinstance(payload, dict) or set(payload) != {"items", "next_cursor"}:
            raise ControlPlaneError("Ronin jobs response violated the protocol")
        items = payload["items"]
        if not isinstance(items, list):
            raise ControlPlaneError("Ronin jobs response items must be a list")
        next_cursor = _protocol_cursor(payload["next_cursor"], name="next_cursor", nullable=True)
        return {"items": [_job(item) for item in items], "next_cursor": next_cursor}

    def events(
        self,
        job_id: str,
        *,
        since: str | None,
        limit: int = 50,
    ) -> dict[str, object]:
        query = {"limit": str(limit)}
        if since is not None:
            query["since"] = since
        payload = self.request("GET", f"/v1/jobs/{quote(job_id, safe='')}/events", query=query)
        if not isinstance(payload, dict) or set(payload) != {"items", "next_since"}:
            raise ControlPlaneError("Ronin events response violated the protocol")
        items = payload["items"]
        if not isinstance(items, list):
            raise ControlPlaneError("Ronin events response items must be a list")
        next_since = _protocol_cursor(payload["next_since"], name="next_since", nullable=False)
        return {"items": [_event(item) for item in items], "next_since": next_since}

    def evidence(self, job_id: str) -> tuple[dict[str, object], ...]:
        payload = self.request("GET", f"/v1/jobs/{quote(job_id, safe='')}/evidence")
        if not isinstance(payload, dict) or set(payload) != {"items"}:
            raise ControlPlaneError("Ronin evidence response violated the protocol")
        items = payload["items"]
        if not isinstance(items, list):
            raise ControlPlaneError("Ronin evidence response items must be a list")
        return tuple(_evidence(item) for item in items)

    def cancel(self, job_id: str) -> dict[str, object]:
        return _job(self.request("POST", f"/v1/jobs/{quote(job_id, safe='')}/cancel"))


def _job(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict) or set(payload) != _JOB_FIELDS:
        raise ControlPlaneError("Ronin job response fields violated the protocol")
    job_id = payload.get("id")
    state = payload.get("state")
    failure_code = payload.get("failure_code")
    if not isinstance(job_id, str) or not job_id or job_id != job_id.strip() or len(job_id) > 256:
        raise ControlPlaneError("Ronin job id must be a bounded non-empty string")
    if state not in {"queued", "running", "cancelling", "cancelled", "succeeded", "failed"}:
        raise ControlPlaneError("Ronin job state is invalid")
    if failure_code is not None and not isinstance(failure_code, str):
        raise ControlPlaneError("Ronin failure_code must be a string when present")
    return {"id": job_id, "state": state, "failure_code": failure_code}


def _event(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict) or set(payload) != _EVENT_FIELDS:
        raise ControlPlaneError("Ronin event response fields violated the protocol")
    sequence = payload["sequence"]
    attempt_id = payload["attempt_id"]
    attempt_sequence = payload["attempt_sequence"]
    kind = payload["kind"]
    message = payload["message"]
    occurred_at = payload["occurred_at"]
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 0:
        raise ControlPlaneError("Ronin event sequence is invalid")
    if not isinstance(attempt_id, str) or not attempt_id or len(attempt_id) > 256:
        raise ControlPlaneError("Ronin event attempt_id is invalid")
    if not isinstance(attempt_sequence, int) or isinstance(attempt_sequence, bool) or attempt_sequence < 0:
        raise ControlPlaneError("Ronin event attempt_sequence is invalid")
    if not isinstance(kind, str) or not kind:
        raise ControlPlaneError("Ronin event kind is invalid")
    if not isinstance(message, str):
        raise ControlPlaneError("Ronin event message is invalid")
    if not isinstance(occurred_at, str) or _INSTANT_RE.fullmatch(occurred_at) is None:
        raise ControlPlaneError("Ronin event occurred_at is not a canonical Instant")
    return {key: payload[key] for key in _EVENT_FIELDS}


def _evidence(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict) or set(payload) != _EVIDENCE_FIELDS or payload.get("version") != 1:
        raise ControlPlaneError("Ronin evidence fields violated the v1 protocol")
    availability = payload.get("availability")
    if availability not in {"available", "missing", "tombstoned", "unavailable"}:
        raise ControlPlaneError("Ronin evidence availability is invalid")
    role = payload.get("role")
    cell_id = payload.get("cell_id")
    digest_algorithm = payload.get("digest_algorithm")
    digest = payload.get("digest")
    media_type = payload.get("media_type")
    size_bytes = payload.get("size_bytes")
    reason = payload.get("reason")
    if not isinstance(role, str) or not role:
        raise ControlPlaneError("Ronin evidence role is invalid")
    if cell_id is not None and (not isinstance(cell_id, str) or not cell_id):
        raise ControlPlaneError("Ronin evidence cell_id is invalid")
    if media_type is not None and not isinstance(media_type, str):
        raise ControlPlaneError("Ronin evidence media_type is invalid")
    if availability == "unavailable":
        if any(value is not None for value in (digest_algorithm, digest, size_bytes)):
            raise ControlPlaneError("Unavailable evidence must omit content identity")
        if not isinstance(reason, str) or not reason:
            raise ControlPlaneError("Unavailable evidence must carry a reason")
    else:
        if digest_algorithm != "sha256":
            raise ControlPlaneError("Ronin evidence digest_algorithm is invalid")
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(ch not in "0123456789abcdef" for ch in digest)
        ):
            raise ControlPlaneError("Ronin evidence digest is invalid")
        if not isinstance(size_bytes, int) or isinstance(size_bytes, bool) or size_bytes < 0:
            raise ControlPlaneError("Ronin evidence size_bytes is invalid")
        if reason is not None:
            raise ControlPlaneError("Only unavailable evidence may carry a reason")
    return {key: payload[key] for key in _EVIDENCE_FIELDS}


TERMINAL_STATES = frozenset({"cancelled", "succeeded", "failed"})

__all__ = ("ControlPlaneClient", "ControlPlaneError", "TERMINAL_STATES", "is_loopback_host")
