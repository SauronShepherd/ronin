from studio_migration import check_spark_python_runtime, qualify_spark_runtime


def test_spark_runtime_preflight_rejects_known_python_version_mismatch(monkeypatch) -> None:
    monkeypatch.setenv("PYSPARK_PYTHON", "python311.exe")
    monkeypatch.setenv("RONIN_PYSPARK_WORKER_VERSION", "3.11")
    result = check_spark_python_runtime()
    assert result.compatible is False
    assert "differs" in result.message


def test_spark_qualification_preserves_runtime_failure_evidence(monkeypatch) -> None:
    monkeypatch.setenv("PYSPARK_PYTHON", "python.exe")
    monkeypatch.delenv("RONIN_PYSPARK_WORKER_VERSION", raising=False)
    result = qualify_spark_runtime(lambda: (_ for _ in ()).throw(RuntimeError("worker crashed")))
    assert result.status == "blocked_by_runtime"
    assert "worker crashed" in result.message
    assert result.to_payload()["schema"] == "ronin.migration.spark-qualification/v1"
