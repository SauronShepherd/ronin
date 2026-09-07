"""Thin standard-library client for the supported Ronin v0.1 HTTP job surface."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import Request, urlopen


class ControlPlaneError(RuntimeError):
    """Expected control-plane transport or protocol failure."""


@dataclass(frozen=True, slots=True)
class ControlPlaneClient:
    base_url: str
    token: str
    timeout: float = 30.0

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
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.token}",
        }
        body = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        if idempotency_key is not None:
            headers["Idempotency-Key"] = idempotency_key
        request = Request(url, data=body, headers=headers, method=method)  # noqa: S310
        try:
            with urlopen(request, timeout=self.timeout) as response:  # noqa: S310
                data = response.read(1024 * 1024 + 1)
        except HTTPError as exc:
            try:
                error_body = exc.read(64 * 1024)
                parsed = json.loads(error_body) if error_body else None
            except (OSError, json.JSONDecodeError, UnicodeDecodeError):
                parsed = None
            code = None
            if isinstance(parsed, dict):
                error = parsed.get("error")
                if isinstance(error, dict) and isinstance(error.get("code"), str):
                    code = error["code"]
            suffix = f" [{code}]" if code else ""
            raise ControlPlaneError(f"Ronin API error {exc.code}{suffix}") from exc
        except URLError as exc:
            raise ControlPlaneError("Ronin endpoint unavailable") from exc
        if len(data) > 1024 * 1024:
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
        return {"items": [_job(item) for item in items], "next_cursor": payload["next_cursor"]}

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
        payload = self.request(
            "GET",
            f"/v1/jobs/{quote(job_id, safe='')}/events",
            query=query,
        )
        if not isinstance(payload, dict) or set(payload) != {"items", "next_since"}:
            raise ControlPlaneError("Ronin events response violated the protocol")
        items = payload["items"]
        if not isinstance(items, list):
            raise ControlPlaneError("Ronin events response items must be a list")
        return {"items": [_event(item) for item in items], "next_since": payload["next_since"]}

    def cancel(self, job_id: str) -> dict[str, object]:
        return _job(self.request("POST", f"/v1/jobs/{quote(job_id, safe='')}/cancel"))


def _job(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise ControlPlaneError("Ronin job response must be an object")
    job_id = payload.get("id")
    state = payload.get("state")
    failure_code = payload.get("failure_code")
    if not isinstance(job_id, str) or not job_id:
        raise ControlPlaneError("Ronin job id must be a non-empty string")
    if state not in {"queued", "running", "cancelling", "cancelled", "succeeded", "failed"}:
        raise ControlPlaneError("Ronin job state is invalid")
    if failure_code is not None and not isinstance(failure_code, str):
        raise ControlPlaneError("Ronin failure_code must be a string when present")
    return {"id": job_id, "state": state, "failure_code": failure_code}


def _event(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise ControlPlaneError("Ronin event response item must be an object")
    required = {
        "sequence": int,
        "attempt_id": str,
        "attempt_sequence": int,
        "kind": str,
        "message": str,
        "occurred_at": str,
    }
    for key, expected in required.items():
        if not isinstance(payload.get(key), expected):
            raise ControlPlaneError(f"Ronin event field {key} is invalid")
    return {key: payload[key] for key in required}


TERMINAL_STATES = frozenset({"cancelled", "succeeded", "failed"})

__all__ = ("ControlPlaneClient", "ControlPlaneError", "TERMINAL_STATES")
