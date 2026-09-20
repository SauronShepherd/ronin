from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]


def _service_block(compose: str, name: str, next_name: str | None) -> str:
    start = compose.index(f"  {name}:\n")
    end = len(compose) if next_name is None else compose.index(f"  {next_name}:\n", start + 1)
    return compose[start:end]


def test_compose_mounts_docker_socket_only_in_runner_broker() -> None:
    compose = (_ROOT / "compose.yaml").read_text(encoding="utf-8")
    broker = _service_block(compose, "runner-broker", "worker")
    worker = _service_block(compose, "worker", "cli")

    socket_mount = "/var/run/docker.sock:/var/run/docker.sock"
    assert compose.count(socket_mount) == 1
    assert socket_mount in broker
    assert socket_mount not in worker
    assert 'command: ["ronin-runner-broker"]' in broker
    assert 'command: ["ronin-broker-worker"]' in worker
    assert "ports:" not in broker
    assert "RONIN_RUNNER_BROKER_URL: http://runner-broker:8090" in worker
    assert "RONIN_BIND_POLICY: container-internal" in worker


def test_compose_provides_private_persistent_postgres_for_appliance_profile() -> None:
    compose = (_ROOT / "compose.yaml").read_text(encoding="utf-8")
    postgres = _service_block(compose, "postgres", "server")
    server = _service_block(compose, "server", "runner-broker")

    assert "image: postgres:16.4-alpine" in postgres
    assert "ronin-postgres:/var/lib/postgresql/data" in postgres
    assert '127.0.0.1:${RONIN_POSTGRES_PORT:-5432}:5432' in postgres
    assert "pg_isready" in postgres
    assert "RONIN_STORAGE_BACKEND: postgres" in server
    assert "RONIN_POSTGRES_DSN:" in compose
    assert "condition: service_healthy" in server


def test_postgres_schema_contains_workflow_and_schedule_persistence() -> None:
    from studio_storage.postgres_core import _SCHEMA

    assert "CREATE TABLE IF NOT EXISTS ronin_workflows" in _SCHEMA
    assert "CREATE TABLE IF NOT EXISTS ronin_schedules" in _SCHEMA
    assert "REFERENCES ronin_workflows(workspace_id, workflow_id)" in _SCHEMA


def test_broker_worker_does_not_trigger_container_entrypoint_socket_setup() -> None:
    script = (_ROOT / "docker" / "container-entrypoint.sh").read_text(encoding="utf-8")

    assert '"${1:-}" = "ronin" ] && [ "${2:-}" = "worker"' in script
    assert '"${1:-}" = "ronin-runner-broker"' in script
    assert "ronin-broker-worker" not in script
    assert script.count("prepare_docker_socket") == 3  # definition + two explicit authority paths
    assert script.count("resolve_worker_image") == 3  # definition + two explicit authority paths


def test_broker_processes_are_installed_as_distinct_entrypoints() -> None:
    pyproject = (_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert 'ronin-runner-broker = "studio_runner_broker.entrypoint:main"' in pyproject
    assert 'ronin-broker-worker = "studio_runner_broker.worker_entrypoint:main"' in pyproject
