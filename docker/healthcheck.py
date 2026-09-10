"""Container-local readiness probe without expanding the public HTTP API."""

from __future__ import annotations

import os
import socket
import sys


def main() -> int:
    host = os.environ.get("RONIN_HEALTH_HOST", "127.0.0.1")
    try:
        port = int(os.environ.get("RONIN_PORT", "8080"))
    except ValueError:
        return 2
    try:
        with socket.create_connection((host, port), timeout=2.0):
            return 0
    except OSError:
        return 1


if __name__ == "__main__":
    sys.exit(main())
