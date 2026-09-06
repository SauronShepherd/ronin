from __future__ import annotations

import pytest
from studio_orchestrator import (
    CellExecutionIdentity,
    CellResumeRecord,
    RunId,
    can_resume_cell,
)

A = "a" * 64
B = "b" * 64
C = "c" * 64
D = "d" * 64
E = "e" * 64


def _identity(**overrides: object) -> CellExecutionIdentity:
    values: dict[str, object] = {
        "run_id": RunId("run-1"),
        "cell_id": "cell-1",
        "source_digest": A,
        "repository_digest": B,
        "runtime_digest": C,
        "parameter_digest": D,
        "upstream_result_digests": (E,),
    }
    values.update(overrides)
    return CellExecutionIdentity(**values)  # type: ignore[arg-type]


def _record(identity: CellExecutionIdentity, **overrides: object) -> CellResumeRecord:
    values: dict[str, object] = {
        "run_id": identity.run_id,
        "cell_id": identity.cell_id,
        "state": "succeeded",
        "execution_identity_digest": identity.digest,
        "artifact_digests": (A,),
    }
    values.update(overrides)
    return CellResumeRecord(**values)  # type: ignore[arg-type]


def test_identity_digest_is_deterministic_and_input_sensitive() -> None:
    identity = _identity()
    assert identity.digest == _identity().digest
    assert identity.digest != _identity(source_digest=B).digest
    assert identity.digest != _identity(repository_digest=C).digest
    assert identity.digest != _identity(runtime_digest=D).digest
    assert identity.digest != _identity(parameter_digest=E).digest
    assert identity.digest != _identity(upstream_result_digests=(A,)).digest


def test_matching_succeeded_record_with_verified_artifacts_resumes() -> None:
    identity = _identity()
    assert can_resume_cell(identity, _record(identity), artifacts_verified=True)


@pytest.mark.parametrize(
    ("record_overrides", "artifacts_verified"),
    [
        ({"state": "failed"}, True),
        ({"run_id": RunId("run-2")}, True),
        ({"cell_id": "cell-2"}, True),
        ({"execution_identity_digest": B}, True),
        ({"artifact_digests": ()}, True),
        ({}, False),
    ],
)
def test_resume_fails_closed_on_any_unverified_precondition(
    record_overrides: dict[str, object],
    artifacts_verified: bool,
) -> None:
    identity = _identity()
    assert not can_resume_cell(
        identity,
        _record(identity, **record_overrides),
        artifacts_verified=artifacts_verified,
    )


@pytest.mark.parametrize(
    "field",
    [
        "source_digest",
        "repository_digest",
        "runtime_digest",
        "parameter_digest",
    ],
)
def test_identity_rejects_invalid_digests(field: str) -> None:
    with pytest.raises(ValueError, match="SHA-256"):
        _identity(**{field: "invalid"})


def test_identity_and_record_validate_text_and_nested_digests() -> None:
    with pytest.raises(ValueError, match="cell id"):
        _identity(cell_id=" bad")
    with pytest.raises(ValueError, match="upstream"):
        _identity(upstream_result_digests=("invalid",))
    identity = _identity()
    with pytest.raises(ValueError, match="artifact"):
        _record(identity, artifact_digests=("invalid",))
    with pytest.raises(ValueError, match="cell state"):
        _record(identity, state=" bad")
