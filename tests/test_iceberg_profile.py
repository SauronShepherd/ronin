from __future__ import annotations

from types import SimpleNamespace

import pytest
import studio_lakehouse.iceberg as iceberg
from studio_lakehouse import (
    IcebergPartialWriteError,
    IcebergProviderError,
    IcebergTableStore,
    OpenTableIdentifier,
)


class _NoSuchTableError(Exception):
    pass


class _NamespaceAlreadyExistsError(Exception):
    pass


class _TableAlreadyExistsError(Exception):
    pass


class _Catalog:
    def __init__(self) -> None:
        self.exists = False
        self.append_error: Exception | None = None
        self.cleanup_error: Exception | None = None
        self.create_calls = 0
        self.drop_calls = 0
        self.read_table = None

    def load_table(self, _identifier):
        if self.read_table is not None:
            return self.read_table
        if not self.exists:
            raise _NoSuchTableError
        if self.append_error is not None:

            class _Table:
                def append(_self, _arrow) -> None:
                    raise self.append_error

            return _Table()
        return object()

    def create_namespace(self, _namespace) -> None:
        raise _NamespaceAlreadyExistsError

    def create_table(self, _identifier, *, schema) -> None:
        del schema
        self.create_calls += 1
        self.exists = True

    def drop_table(self, _identifier, *, purge: bool) -> None:
        del purge
        self.drop_calls += 1
        if self.cleanup_error is not None:
            raise self.cleanup_error
        self.exists = False


def _store(monkeypatch: pytest.MonkeyPatch, catalog: _Catalog) -> IcebergTableStore:
    exception_types = {
        "NoSuchTableError": _NoSuchTableError,
        "NamespaceAlreadyExistsError": _NamespaceAlreadyExistsError,
        "TableAlreadyExistsError": _TableAlreadyExistsError,
    }
    monkeypatch.setattr(iceberg, "_pyiceberg_catalog", lambda: lambda *_a, **_k: catalog)
    monkeypatch.setattr(
        iceberg,
        "_pyiceberg_exception_type",
        lambda name: exception_types[name],
    )
    monkeypatch.setattr(iceberg, "_rows_table", lambda _rows: SimpleNamespace(schema=object()))
    return IcebergTableStore()


def test_iceberg_lookup_distinguishes_missing_from_catalog_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _store(monkeypatch, _Catalog())
    identifier = OpenTableIdentifier(("analytics",), "events")
    with pytest.raises(FileNotFoundError, match="does not exist"):
        store._load(identifier)  # noqa: SLF001 - exercise provider error mapping

    class _UnavailableCatalog(_Catalog):
        def load_table(self, _identifier):
            raise RuntimeError("catalog is unavailable")

    unavailable = _store(monkeypatch, _UnavailableCatalog())
    with pytest.raises(IcebergProviderError, match="lookup failed"):
        unavailable._load(identifier)  # noqa: SLF001 - exercise provider error mapping


def test_iceberg_create_failure_removes_the_new_table(monkeypatch: pytest.MonkeyPatch) -> None:
    catalog = _Catalog()
    catalog.append_error = RuntimeError("append failed")
    store = _store(monkeypatch, catalog)

    with pytest.raises(IcebergProviderError, match="new table was removed"):
        store.write_rows(
            OpenTableIdentifier(("analytics",), "events"),
            ({"id": 1},),
            mode="create",
        )

    assert catalog.create_calls == 1
    assert catalog.drop_calls == 1
    assert not catalog.exists


def test_iceberg_create_cleanup_failure_is_explicit_and_not_reported_as_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog = _Catalog()
    catalog.append_error = RuntimeError("append failed")
    catalog.cleanup_error = RuntimeError("drop failed")
    store = _store(monkeypatch, catalog)

    with pytest.raises(IcebergPartialWriteError, match="cleanup of the new table also failed"):
        store.write_rows(
            OpenTableIdentifier(("analytics",), "events"),
            ({"id": 1},),
            mode="create",
        )

    assert catalog.drop_calls == 1
    assert catalog.exists


def test_iceberg_catalog_preflight_failure_does_not_start_create(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _UnavailableCatalog(_Catalog):
        def load_table(self, _identifier):
            raise RuntimeError("catalog is unavailable")

    catalog = _UnavailableCatalog()
    store = _store(monkeypatch, catalog)

    with pytest.raises(IcebergProviderError, match="preflight failed"):
        store.write_rows(
            OpenTableIdentifier(("analytics",), "events"),
            ({"id": 1},),
            mode="create",
        )

    assert catalog.create_calls == 0


class _Batch:
    def __init__(self, rows, *, nbytes: int) -> None:
        self.rows = rows
        self.nbytes = nbytes

    def slice(self, offset: int, length: int) -> _Batch:
        return _Batch(self.rows[offset : offset + length], nbytes=self.nbytes)

    def to_pylist(self):
        return self.rows


class _TableScan:
    def __init__(self, batches) -> None:
        self.batches = batches

    def to_arrow_batch_reader(self):
        return iter(self.batches)

    def to_arrow(self):
        raise AssertionError("Iceberg bounded reads must not materialize the full scan")


class _ReadTable:
    def __init__(self, batches) -> None:
        self.scan_result = _TableScan(batches)
        self.scan_arguments = None

    def scan(self, **kwargs):
        self.scan_arguments = kwargs
        return self.scan_result


def _read_store(monkeypatch: pytest.MonkeyPatch, batches):
    catalog = _Catalog()
    catalog.exists = True
    table = _ReadTable(batches)
    catalog.read_table = table
    store = _store(monkeypatch, catalog)
    return store, table


def test_iceberg_read_applies_row_limit_to_streaming_scan(monkeypatch: pytest.MonkeyPatch) -> None:
    store, table = _read_store(
        monkeypatch,
        [_Batch([{"id": 1}, {"id": 2}, {"id": 3}], nbytes=30)],
    )

    with pytest.raises(ValueError, match="requested row limit"):
        store.read_rows(OpenTableIdentifier(("analytics",), "events"), limit=2)

    assert table.scan_arguments["limit"] == 3
    assert table.scan_arguments["selected_fields"] == ("*",)


def test_iceberg_read_enforces_byte_budget_before_row_conversion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, _table = _read_store(monkeypatch, [_Batch([{"id": 1}], nbytes=101)])

    with pytest.raises(ValueError, match="configured byte budget"):
        store.read_rows(
            OpenTableIdentifier(("analytics",), "events"),
            max_bytes=100,
        )


@pytest.mark.parametrize("timeout", [float("nan"), float("inf"), 0, 3601])
def test_iceberg_read_rejects_invalid_time_budget_before_catalog_io(
    monkeypatch: pytest.MonkeyPatch,
    timeout: float,
) -> None:
    class _NoCatalogIO(_Catalog):
        def load_table(self, _identifier):
            raise AssertionError("invalid time budget must fail before provider IO")

    store = _store(monkeypatch, _NoCatalogIO())
    with pytest.raises(ValueError, match="max_elapsed_seconds"):
        store.read_rows(
            OpenTableIdentifier(("analytics",), "events"),
            max_elapsed_seconds=timeout,
        )
