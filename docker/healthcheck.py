"""Container-local HTTP readiness probe outside the versioned public API."""

from __future__ import annotations

import http.client
import os
import sys

_READY_BODY = b'{"status":"ready"}'
_MAX_BODY_BYTES = 64


def main() -> int:
    host = os.environ.get("RONIN_HEALTH_HOST", "127.0.0.1")
    if not host or host != host.strip():
        return 2
    try:
        port = int(os.environ.get("RONIN_PORT", "8080"))
    except ValueError:
        return 2
    if not 1 <= port <= 65535:
        return 2

    connection = http.client.HTTPConnection(host, port, timeout=2.0)
    try:
        connection.request("GET", "/healthz", headers={"Accept": "application/json"})
        response = connection.getresponse()
        body = response.read(_MAX_BODY_BYTES + 1)
    except (OSError, http.client.HTTPException):
        return 1
    finally:
        connection.close()

    if len(body) > _MAX_BODY_BYTES:
        return 1
    if response.status != 200 or response.getheader("Content-Type") != "application/json":
        return 1
    return 0 if body == _READY_BODY else 1


if __name__ == "__main__":
    sys.exit(main())
