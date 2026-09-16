from __future__ import annotations

from studio_orchestrator import JobStore
from studio_storage import PostgresJobReadPort


def test_postgres_adapter_exposes_the_complete_job_store_surface() -> None:
    required = {
        "create_job",
        "get_job",
        "get_run_id_for_job",
        "list_jobs",
        "request_cancel",
        "claim_next_run",
        "heartbeat",
        "append_events",
        "read_event_page",
        "read_events",
        "put_cell_result",
        "read_cell_results",
        "put_evidence",
        "read_evidence",
        "complete_attempt",
        "reclaim_expired",
    }
    assert required <= set(PostgresJobReadPort.__dict__)


def _protocol_assignment(store: PostgresJobReadPort) -> JobStore:
    return store


def test_postgres_adapter_is_assignable_to_job_store_protocol() -> None:
    # The explicit assignment is checked by mypy; constructing the adapter is
    # intentionally avoided because this test suite does not require a live DB.
    assert callable(_protocol_assignment)
