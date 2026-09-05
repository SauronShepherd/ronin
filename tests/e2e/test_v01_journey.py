"""Ronin v0.1 acceptance journey.

Every step maps 1:1 to docs/product/V01_SCOPE.md section 4. Tests unskip as their
capability lands. All fifteen must pass before v0.1 is tagged.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.e2e


@pytest.mark.skip(reason="W6: compose file does not exist yet")
def test_step_01_compose_reaches_healthy_within_60s() -> None: ...


@pytest.mark.skip(reason="W5: ronin doctor does not exist yet")
def test_step_02_doctor_reports_all_checks_passing() -> None: ...


@pytest.mark.skip(reason="W5: ronin validate does not exist yet")
def test_step_03_validate_accepts_demo_project() -> None: ...


@pytest.mark.skip(reason="W5: ronin plan does not exist yet")
def test_step_04_plan_prints_order_and_levels() -> None: ...


@pytest.mark.skip(reason="W4: POST /v1/jobs does not exist yet")
def test_step_05_submit_returns_queued_job() -> None: ...


@pytest.mark.skip(reason="W3: worker does not exist yet")
def test_step_06_worker_claims_and_executes_first_cells() -> None: ...


@pytest.mark.skip(reason="W3: lease reclamation does not exist yet")
def test_step_07_kill_worker_orphans_lease() -> None: ...


@pytest.mark.skip(reason="W3: lease reclamation does not exist yet")
def test_step_08_restart_waits_for_lease_expiry() -> None: ...


@pytest.mark.skip(reason="W3: per-cell resume does not exist yet")
def test_step_09_reclaimed_attempt_resumes_at_cell_four() -> None: ...


@pytest.mark.skip(reason="W4: GET /v1/jobs/{id} does not exist yet")
def test_step_10_job_reaches_succeeded() -> None: ...


@pytest.mark.skip(reason="W4: events endpoint does not exist yet")
def test_step_11_events_contiguous_across_attempts_with_terminal() -> None: ...


@pytest.mark.skip(reason="W4: evidence endpoint does not exist yet")
def test_step_12_evidence_present_for_all_six_cells() -> None: ...


@pytest.mark.skip(reason="W4: idempotency does not exist yet")
def test_step_13_replayed_idempotency_key_returns_same_job() -> None: ...


@pytest.mark.skip(reason="W4: cancel does not exist yet")
def test_step_14_cancel_removes_container() -> None: ...


@pytest.mark.skip(reason="W4: SDK contract alignment not done yet")
def test_step_15_sdk_round_trip_matches_cli() -> None: ...


def test_journey_progress_is_reported(record_property: pytest.FixtureRequest) -> None:
    del record_property
    steps = [name for name in globals() if name.startswith("test_step_")]
    assert len(steps) == 15
