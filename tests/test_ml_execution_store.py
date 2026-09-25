from studio_ml import ExecutionSnapshot, SqliteExecutionStore


def test_sqlite_execution_store_survives_reopen(tmp_path) -> None:
    path = tmp_path / "ml.sqlite"
    first = SqliteExecutionStore(path)
    first.put(
        ExecutionSnapshot("run-1", "succeeded", result_payload={"metrics": {"accuracy": 1.0}})
    )
    second = SqliteExecutionStore(path)
    restored = second.get("run-1")
    assert restored is not None
    assert restored.run_id == "run-1"
    assert restored.state == "succeeded"
    assert restored.to_payload()["result"] == {"metrics": {"accuracy": 1.0}}
