from __future__ import annotations

import os
import secrets
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("RONIN_REAL_DOCKER_QUALIFICATION") != "1",
    reason="opt-in Docker qualification starts isolated Ronin and PostgreSQL services",
)


def _run(command: list[str], *, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    # Commands are fixed Docker/PostgreSQL utilities and this checkout's backup CLI.
    return subprocess.run(  # noqa: S603
        command, check=True, capture_output=True, text=True, env=env
    )


def test_appliance_backup_restores_postgres_and_local_data_volume(tmp_path: Path) -> None:
    """Restore the database and Ronin's local-data volume from one real bundle."""
    compose_file = tmp_path / "compose.yaml"
    project = f"ronin-backup-{secrets.token_hex(6)}"
    password = secrets.token_urlsafe(24)
    image = os.environ.get("RONIN_DOCKER_QUALIFICATION_IMAGE", "")
    assert image.startswith("sha256:"), "Docker qualification must supply the immutable Ronin image"
    compose_file.write_text(
        "services:\n"
        "  postgres:\n"
        "    image: postgres:16.4-alpine\n"
        "    environment:\n"
        "      POSTGRES_DB: ronin\n"
        "      POSTGRES_USER: ronin\n"
        f"      POSTGRES_PASSWORD: {password}\n"
        "  server:\n"
        f"    image: {image}\n"
        "    init: true\n"
        "    command: [python, -c, 'import time; time.sleep(3600)']\n"
        "    environment:\n"
        "      RONIN_ARTIFACT_BACKEND: local\n"
        "      RONIN_DATA_DIR: /var/lib/ronin\n"
        "    volumes:\n"
        "      - ronin-data:/var/lib/ronin\n"
        "volumes:\n"
        "  ronin-data:\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env.update(
        {
            "COMPOSE_PROJECT_NAME": project,
            "POSTGRES_USER": "ronin",
            "POSTGRES_DB": "ronin",
            "POSTGRES_PASSWORD": password,
            "RONIN_TOKEN": secrets.token_urlsafe(32),
            "RONIN_RUNNER_BROKER_TOKEN": secrets.token_urlsafe(32),
        }
    )
    compose = ["docker", "compose", "-f", str(compose_file)]
    try:
        _run(compose + ["up", "-d", "postgres", "server"], env=env)
        deadline = time.monotonic() + 60
        while True:
            ready = subprocess.run(  # noqa: S603
                compose + ["exec", "-T", "postgres", "pg_isready", "-U", "ronin", "-d", "ronin"],
                capture_output=True,
                text=True,
                env=env,
            )
            if ready.returncode == 0:
                break
            if time.monotonic() >= deadline:
                raise AssertionError(f"isolated PostgreSQL did not become ready: {ready.stderr}")
            time.sleep(0.25)

        _run(
            compose
            + [
                "exec",
                "-T",
                "postgres",
                "psql",
                "-U",
                "ronin",
                "-d",
                "ronin",
                "-v",
                "ON_ERROR_STOP=1",
                "-c",
                "CREATE TABLE backup_probe (value text NOT NULL); "
                "INSERT INTO backup_probe VALUES ('before-backup');",
            ],
            env=env,
        )
        _run(
            compose
            + [
                "exec",
                "-T",
                "server",
                "python",
                "-c",
                "from pathlib import Path; root=Path('/var/lib/ronin'); "
                "(root/'artifacts').mkdir(parents=True, exist_ok=True); "
                "(root/'execution-evidence').mkdir(parents=True, exist_ok=True); "
                "(root/'artifacts'/'probe.bin').write_bytes(b'before-backup'); "
                "(root/'execution-evidence'/'run.json').write_text('before-backup')",
            ],
            env=env,
        )

        bundle = tmp_path / "appliance-backup"
        _run(
            [
                sys.executable,
                "-m",
                "tools.ronin_appliance_backup",
                "--compose-file",
                str(compose_file),
                "--backup-appliance",
                str(bundle),
            ],
            env=env,
        )
        assert (bundle / "postgres.dump").is_file()
        assert (bundle / "postgres.dump.sha256").is_file()
        assert (bundle / "data" / "artifacts" / "probe.bin").read_bytes() == b"before-backup"
        assert (bundle / "data" / "execution-evidence" / "run.json").read_text() == "before-backup"
        assert (bundle / "ronin-appliance-backup.json").is_file()

        _run(
            compose
            + [
                "exec",
                "-T",
                "postgres",
                "psql",
                "-U",
                "ronin",
                "-d",
                "ronin",
                "-v",
                "ON_ERROR_STOP=1",
                "-c",
                "INSERT INTO backup_probe VALUES ('after-backup');",
            ],
            env=env,
        )
        _run(
            compose
            + [
                "exec",
                "-T",
                "server",
                "python",
                "-c",
                "from pathlib import Path; root=Path('/var/lib/ronin'); "
                "(root/'artifacts'/'probe.bin').write_bytes(b'after-backup'); "
                "(root/'execution-evidence'/'run.json').write_text('after-backup')",
            ],
            env=env,
        )
        _run(
            [
                sys.executable,
                "-m",
                "tools.ronin_appliance_backup",
                "--compose-file",
                str(compose_file),
                "--restore-appliance",
                str(bundle),
                "--force",
            ],
            env=env,
        )

        restored = _run(
            compose
            + [
                "exec",
                "-T",
                "postgres",
                "psql",
                "-U",
                "ronin",
                "-d",
                "ronin",
                "-At",
                "-c",
                "SELECT string_agg(value, ',' ORDER BY value) FROM backup_probe;",
            ],
            env=env,
        )
        assert restored.stdout.strip() == "before-backup"
        restored_files = _run(
            compose
            + [
                "exec",
                "-T",
                "server",
                "python",
                "-c",
                "from pathlib import Path; root=Path('/var/lib/ronin'); "
                "print((root/'artifacts'/'probe.bin').read_bytes().decode() + ':' + "
                "(root/'execution-evidence'/'run.json').read_text())",
            ],
            env=env,
        )
        assert restored_files.stdout.strip() == "before-backup:before-backup"
    finally:
        subprocess.run(  # noqa: S603
            compose + ["down", "--volumes", "--remove-orphans"],
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )
