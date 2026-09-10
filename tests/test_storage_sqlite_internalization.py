import studio_storage
import studio_storage.paged_store as paged_store
from studio_storage.fenced_sqlite import SqliteJobStore
from studio_storage.sqlite import _SqliteLifecycleStore


def test_sqlite_lifecycle_helper_has_no_supported_worker_mutations_or_paging() -> None:
    assert issubclass(SqliteJobStore, _SqliteLifecycleStore)
    assert not hasattr(_SqliteLifecycleStore, "list_jobs")
    assert not hasattr(_SqliteLifecycleStore, "read_event_page")
    assert not hasattr(_SqliteLifecycleStore, "append_events")
    assert not hasattr(_SqliteLifecycleStore, "put_cell_result")
    assert not hasattr(_SqliteLifecycleStore, "put_evidence")
    assert not hasattr(_SqliteLifecycleStore, "complete_attempt")


def test_supported_sqlite_adapter_owns_worker_mutations_and_service_paging() -> None:
    for method in (
        "list_jobs",
        "read_event_page",
        "append_events",
        "put_cell_result",
        "put_evidence",
        "complete_attempt",
    ):
        assert method in SqliteJobStore.__dict__


def test_supported_sqlite_adapter_has_single_public_export() -> None:
    assert studio_storage.SqliteJobStore is SqliteJobStore
    assert "SqliteJobStore" not in paged_store.__dict__
    assert "SqliteJobStore" not in paged_store.__all__
