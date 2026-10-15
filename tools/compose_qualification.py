"""Static fail-closed qualification for the Ronin Compose appliance contract."""

from __future__ import annotations

from pathlib import Path


class ComposeQualificationError(ValueError):
    pass


def qualify_compose(path: Path) -> tuple[str, ...]:
    text = path.read_text(encoding="utf-8")
    required = (
        "postgres:",
        "server:",
        "runner-broker:",
        "worker:",
        "ronin-postgres:/var/lib/postgresql/data",
        "condition: service_healthy",
        "RONIN_STORAGE_BACKEND: postgres",
        "RONIN_RUNNER_BROKER_TOKEN",
        "/var/run/docker.sock:/var/run/docker.sock",
    )
    missing = tuple(item for item in required if item not in text)
    if missing:
        raise ComposeQualificationError(f"compose contract is missing: {', '.join(missing)}")
    if text.count("/var/run/docker.sock:/var/run/docker.sock") != 1:
        raise ComposeQualificationError("Docker socket must be mounted only by runner-broker")
    if 'ports:\n      - "127.0.0.1:${RONIN_POSTGRES_PORT' not in text:
        raise ComposeQualificationError("PostgreSQL port must remain loopback-only")
    return required


__all__ = ("ComposeQualificationError", "qualify_compose")
