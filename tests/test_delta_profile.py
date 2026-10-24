from __future__ import annotations

import pytest
from studio_lakehouse import (
    DeltaCompatibilityProfile,
    DeltaTableStore,
    OpenTableIdentifier,
)


def test_delta_profile_declares_supported_boundary() -> None:
    profile = DeltaCompatibilityProfile()
    assert profile.protocol_version == 1
    assert profile.supports_write("create")
    assert profile.supports_write("delete")
    assert "schema-evolution" in profile.unsupported_features


def test_delta_store_validates_mode_before_optional_dependency_loading(tmp_path) -> None:
    store = DeltaTableStore(tmp_path)
    assert store.compatibility.protocol_version == 1
    with pytest.raises(ValueError, match="unsupported Delta write mode"):
        store.write_rows(
            OpenTableIdentifier(("analytics",), "events"),
            ({"id": 1},),
            mode="invalid",  # type: ignore[arg-type]
        )


def test_delta_delete_removes_only_a_table_inside_the_warehouse(tmp_path) -> None:
    store = DeltaTableStore(tmp_path)
    identifier = OpenTableIdentifier(("analytics",), "events")
    table_path = tmp_path / "analytics" / "events"
    (table_path / "_delta_log").mkdir(parents=True)
    (table_path / "data.parquet").write_bytes(b"test")

    store.delete_table(identifier)

    assert not table_path.exists()
    with pytest.raises(FileNotFoundError, match="Delta table does not exist"):
        store.delete_table(identifier)


def test_delta_store_validates_projection_and_version_before_optional_dependency_loading(
    tmp_path,
) -> None:
    store = DeltaTableStore(tmp_path)
    identifier = OpenTableIdentifier(("analytics",), "events")
    with pytest.raises(ValueError, match="non-empty and trimmed"):
        store.read_rows(identifier, columns=(" id",))
    with pytest.raises(ValueError, match="non-negative"):
        store.read_rows(identifier, version="-1")


class _Batch:
    def __init__(self, rows, *, nbytes: int) -> None:
        self.rows = rows
        self.nbytes = nbytes
        self.num_rows = len(rows)

    def slice(self, offset: int, length: int) -> _Batch:
        return _Batch(self.rows[offset : offset + length], nbytes=self.nbytes)

    def to_pylist(self):
        return self.rows


class _Scanner:
    def __init__(self, batches) -> None:
        self.batches = batches
        self.read_count = 0

    def to_batches(self):
        for batch in self.batches:
            self.read_count += 1
            yield batch


def _delta_read_fixture(monkeypatch, batches):
    from types import SimpleNamespace

    import studio_lakehouse.delta as delta

    scanner = _Scanner(batches)

    class _Dataset:
        def scanner(self, **kwargs):
            assert kwargs["batch_size"] <= 1024
            assert kwargs["batch_readahead"] == 1
            assert kwargs["fragment_readahead"] == 1
            assert kwargs["use_threads"] is False
            return scanner

    class _Table:
        def to_pyarrow_dataset(self):
            return _Dataset()

        def to_pyarrow_table(self, **_kwargs):
            raise AssertionError("bounded Delta reads must not materialize the full table")

    monkeypatch.setattr(
        delta, "_deltalake", lambda: SimpleNamespace(DeltaTable=lambda *_a, **_k: _Table())
    )
    return scanner


def test_delta_read_applies_row_limit_during_streaming_scan(tmp_path, monkeypatch) -> None:
    scanner = _delta_read_fixture(
        monkeypatch,
        [_Batch([{"id": 1}, {"id": 2}, {"id": 3}], nbytes=30)],
    )
    store = DeltaTableStore(tmp_path)
    identifier = OpenTableIdentifier(("analytics",), "events")

    with pytest.raises(ValueError, match="requested row limit"):
        store.read_rows(identifier, limit=2)

    assert scanner.read_count == 1


def test_delta_read_enforces_byte_budget_before_row_conversion(tmp_path, monkeypatch) -> None:
    batch = _Batch([{"id": 1}], nbytes=101)
    scanner = _delta_read_fixture(monkeypatch, [batch])
    store = DeltaTableStore(tmp_path)
    identifier = OpenTableIdentifier(("analytics",), "events")

    with pytest.raises(ValueError, match="configured byte budget"):
        store.read_rows(identifier, max_bytes=100)

    assert scanner.read_count == 1


@pytest.mark.parametrize("timeout", [float("nan"), float("inf"), float("-inf"), 0, 3601])
def test_delta_read_rejects_invalid_time_budgets_before_loading_provider(
    tmp_path, monkeypatch, timeout
) -> None:
    import studio_lakehouse.delta as delta

    monkeypatch.setattr(
        delta,
        "_deltalake",
        lambda: pytest.fail("invalid budgets must fail before loading the provider"),
    )
    with pytest.raises(ValueError, match="max_elapsed_seconds"):
        DeltaTableStore(tmp_path).read_rows(
            OpenTableIdentifier(("analytics",), "events"),
            max_elapsed_seconds=timeout,
        )
