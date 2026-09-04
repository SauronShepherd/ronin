from __future__ import annotations

from typing import cast

import pytest
from studio_kernel import ExecutorIsolation, SessionPolicy
from studio_kernel.session import IsolationQualification


def _evidenced(status: IsolationQualification) -> ExecutorIsolation:
    return ExecutorIsolation(
        "container",
        True,
        True,
        True,
        status,
        "ronin/docker-isolation",
        "1",
        "docker/engine@27.5.1",
        "local-evidence://qualification/docker.json",
    )


def test_isolation_claim_defaults_to_declared_without_evidence() -> None:
    claim = ExecutorIsolation("container", True, True, True)
    assert claim.qualification_status == "declared"
    assert claim.qualification_scheme is None
    assert claim.qualification_version is None
    assert claim.runtime_identity is None
    assert claim.evidence_ref is None


def test_declared_claim_cannot_smuggle_qualification_evidence() -> None:
    with pytest.raises(ValueError, match="must not carry"):
        ExecutorIsolation(
            "container",
            True,
            True,
            True,
            qualification_scheme="unverified",
        )


def test_evidenced_claim_requires_complete_clean_metadata() -> None:
    with pytest.raises(ValueError, match="complete qualification evidence"):
        ExecutorIsolation(
            "container",
            True,
            True,
            True,
            "tested",
            "ronin/docker-isolation",
            "1",
            "docker/engine@27.5.1",
        )

    with pytest.raises(ValueError, match="runtime identity"):
        ExecutorIsolation(
            "container",
            True,
            True,
            True,
            "tested",
            "ronin/docker-isolation",
            "1",
            " docker/engine@27.5.1",
            "local-evidence://qualification/docker.json",
        )

    tested = _evidenced("tested")
    qualified = _evidenced("qualified")
    assert tested.qualification_status == "tested"
    assert qualified.evidence_ref == "local-evidence://qualification/docker.json"


def test_isolation_claim_and_policy_reject_unknown_qualification_values() -> None:
    with pytest.raises(ValueError, match="qualification status"):
        ExecutorIsolation(
            "container",
            True,
            True,
            True,
            cast(IsolationQualification, "certified"),
        )
    with pytest.raises(ValueError, match="minimum isolation qualification"):
        SessionPolicy(minimum_isolation_qualification=cast(IsolationQualification, "certified"))


def test_session_policy_can_require_tested_or_qualified_isolation() -> None:
    declared = ExecutorIsolation("container", True, True, True)
    tested = _evidenced("tested")
    qualified = _evidenced("qualified")

    SessionPolicy().validate_isolation(declared)
    SessionPolicy(minimum_isolation_qualification="tested").validate_isolation(tested)
    SessionPolicy(minimum_isolation_qualification="tested").validate_isolation(qualified)
    SessionPolicy(minimum_isolation_qualification="qualified").validate_isolation(qualified)

    with pytest.raises(ValueError, match="below session policy minimum"):
        SessionPolicy(minimum_isolation_qualification="tested").validate_isolation(declared)
    with pytest.raises(ValueError, match="below session policy minimum"):
        SessionPolicy(minimum_isolation_qualification="qualified").validate_isolation(tested)
