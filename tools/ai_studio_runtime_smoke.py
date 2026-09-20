"""Validate a running OpenAI-compatible local runtime."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlsplit


def _url(base_url: str, path: str) -> str:
    if urlsplit(base_url).scheme not in {"http", "https"}:
        raise ValueError("base URL must use http or https")
    return f"{base_url.rstrip('/')}{path}"


def _get(base_url: str, path: str, timeout: float) -> Any:
    request = urllib.request.Request(_url(base_url, path), method="GET")  # noqa: S310
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        return json.loads(response.read(16 * 1024 * 1024))


def _post(base_url: str, path: str, payload: dict[str, object], timeout: float) -> Any:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(  # noqa: S310
        _url(base_url, path), data=body, method="POST",  # noqa: S310
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        return json.loads(response.read(16 * 1024 * 1024))


def run(base_url: str, model: str, timeout: float) -> dict[str, object]:
    models = _get(base_url, "/v1/models", timeout)
    advertised = [item.get("id") for item in models.get("data", []) if isinstance(item, dict)]
    if model not in advertised:
        raise RuntimeError(f"model {model!r} is not advertised by runtime")
    response = _post(
        base_url, "/v1/chat/completions",
        {"model": model, "messages": [{"role": "user", "content": "ping"}], "max_tokens": 1},
        timeout,
    )
    if not isinstance(response, dict) or not response.get("choices"):
        raise RuntimeError("runtime returned no choices")
    return {
        "status": "passed", "base_url": base_url, "model": model,
        "choices": len(response["choices"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--timeout", type=float, default=15.0)
    args = parser.parse_args()
    try:
        print(json.dumps(run(args.base_url, args.model, args.timeout), indent=2))
    except (OSError, ValueError, RuntimeError, urllib.error.URLError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
