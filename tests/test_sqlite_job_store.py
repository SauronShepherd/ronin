from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from studio_orchestrator import AttemptId, Job, JobId, JobState, LeaseToken, Run, RunId, RunState
from studio_storage import SqliteJobStore, open_database, schema_version

NOW = "2026-09-06T09:00:00Z"


def _job() -> Job:
    return Job(
        JobId("job-1"),
        "project-1",
        "key-1",
        "a" * 64,
        JobState.QUEUED,
        NOW,
        NOW,
    )


def _run() -> Run:
    return Run(RunId("run-1"), JobId("job-1"), 1, RunState.PENDING, NOW, NOW, NOW)


def test_sqlite_configuration_migration_and_reopen(tmp_path: Path) -> None:
    path = tmp_path / "data" / "ronin.db"
    store = SqliteJobStore(path, migration_now=NOW)
    assert store.create_job(_job(), _run()).id == JobId("job-1")

    connection = open_database(path)
    try:
        assert schema_version(connection) == 1
        assert connection.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert connection.execute("PRAGMA synchronous").fetchone()[0] == 2
        assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
    finally:
        connection.close()

    reopened = SqliteJobStore(path, migration_now=NOW)
    restored = reopened.get_job(JobId("job-1"))
    assert restored is not None
    assert restored.id == JobId("job-1")


def test_newer_schema_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "ronin.db"
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    connection.execute("INSERT INTO schema_migrations VALUES (99, ?)", (NOW,))
    connection.commit()
    connection.close()

    try:
        SqliteJobStore(path, migration_now=NOW)
    except RuntimeError as exc:
        assert "newer than supported" in str(exc)
    else:
        raise AssertionError("newer schema must fail closed")


def test_twenty_concurrent_claimers_have_one_winner(tmp_path: Path) -> None:
    store = SqliteJobStore(tmp_path / "ronin.db", migration_now=NOW)
    store.create_job(_job(), _run())

    def claim(index: int):
        return store.claim_next_run(
            owner=f"worker-{index}",
            lease_token=LeaseToken(f"lease-{index}"),
            attempt_id=AttemptId(f"attempt-{index}"),
            lease_seconds=30,
            now=NOW,
        )

    with ThreadPoolExecutor(max_workers=20) as executor:
        results = list(executor.map(claim, range(20)))

    winners = [result for result in results if result is not None]
    assert len(winners) == 1
    assert winners[0].run.id == RunId("run-1")
