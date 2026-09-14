"""Installed process entrypoint for the constrained runner broker."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from .server import RunnerBrokerConfig, RunnerBrokerServer


def _env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if value is None or not value or value != value.strip():
        raise ValueError(f"{name} must be set to a non-empty trimmed value")
    return value


def main() -> int:
    try:
        port = int(_env("RONIN_RUNNER_BROKER_PORT", "8090"))
        if not 1 <= port <= 65535:
            raise ValueError("RONIN_RUNNER_BROKER_PORT must be between 1 and 65535")
        data_dir = Path(_env("RONIN_DATA_DIR", ".ronin")).expanduser().resolve()
        config = RunnerBrokerConfig(
            token=_env("RONIN_RUNNER_BROKER_TOKEN"),
            image=_env("RONIN_IMAGE"),
            evidence_root=data_dir / "execution-evidence",
        )
        server = RunnerBrokerServer(
            (_env("RONIN_RUNNER_BROKER_HOST", "127.0.0.1"), port),
            config,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 130
    finally:
        server.server_close()
    return 0


__all__ = ("main",)
