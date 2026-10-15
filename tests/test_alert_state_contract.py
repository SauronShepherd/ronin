from studio_observability import AlertInstance

_T0 = "2026-09-13T10:00:00.000000Z"


def test_alert_state_contract_supports_pending_and_firing_transitions() -> None:
    pending = AlertInstance("rule", "fingerprint", "pending", 0.0, _T0, _T0)
    assert pending.is_active
    assert not pending.is_firing
    firing = AlertInstance("rule", "fingerprint", "firing", 2.0, _T0, _T0)
    assert firing.is_active
    assert firing.is_firing
