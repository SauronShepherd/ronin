from studio_execution import (
    InMemoryExecutionBackend,
    WorkloadSpec,
    WorkloadState,
)


def spec(run_id: str = "run-1") -> WorkloadSpec:
    return WorkloadSpec(
        run_id=run_id,
        worker_protocol="plugin-worker/v1",
        image="ronin-worker@sha256:abc",
        command=("ronin-worker", "--serve"),
    )


def test_submit_is_idempotent_and_evidence_is_runtime_neutral() -> None:
    backend = InMemoryExecutionBackend()
    first = backend.submit(spec())
    second = backend.submit(spec())
    assert first == second
    assert backend.get_status(first).state is WorkloadState.SUBMITTED
    evidence = backend.collect_evidence(first)
    assert evidence.runtime_fingerprint == "in-memory/test"


def test_cancel_is_terminal_and_delete_removes_workload() -> None:
    backend = InMemoryExecutionBackend()
    handle = backend.submit(spec())
    backend.cancel(handle, "user requested")
    assert backend.get_status(handle).state is WorkloadState.CANCELLED
    backend.delete(handle)
    try:
        backend.get_status(handle)
    except KeyError:
        pass
    else:
        raise AssertionError("deleted workload remained addressable")


def test_workload_spec_rejects_unbounded_or_ambiguous_inputs() -> None:
    try:
        WorkloadSpec("run", "plugin-worker/v1", "image", command=(), timeout_seconds=0)
    except ValueError:
        pass
    else:
        raise AssertionError("invalid workload spec was accepted")
