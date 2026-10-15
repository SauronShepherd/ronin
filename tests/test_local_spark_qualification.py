from __future__ import annotations

import subprocess

from tools import local_spark_qualification as qualification


def test_run_bounded_reports_timeout_without_claiming_success(monkeypatch) -> None:
    def timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd="spark", timeout=3)

    monkeypatch.setattr(qualification.subprocess, "run", timeout)
    assert qualification.run_bounded(3) == {
        "status": "timeout",
        "provider": "pyspark-local",
        "timeout_seconds": 3,
    }


def test_run_bounded_rejects_non_object_worker_output(monkeypatch) -> None:
    class Completed:
        returncode = 0
        stdout = "[]"

    monkeypatch.setattr(qualification.subprocess, "run", lambda *_args, **_kwargs: Completed())
    assert qualification.run_bounded(3) == {
        "status": "failed",
        "provider": "pyspark-local",
        "error": "ValueError",
    }
