from __future__ import annotations

import pytest
from studio_orchestrator import Lease, LeaseToken

ACQUIRED = "2026-09-06T09:00:00.000000Z"
HEARTBEAT = "2026-09-06T09:00:10.000000Z"
EXPIRY = "2026-09-06T09:00:30.000000Z"


def test_lease_rejects_heartbeat_before_acquisition() -> None:
    with pytest.raises(ValueError, match="heartbeat_at must not precede"):
        Lease(
            owner="worker-1",
            token=LeaseToken("token-1"),
            acquired_at=HEARTBEAT,
            heartbeat_at=ACQUIRED,
            expires_at=EXPIRY,
        )


def test_lease_rejects_expiry_at_or_before_heartbeat() -> None:
    with pytest.raises(ValueError, match="expires_at must be after heartbeat_at"):
        Lease(
            owner="worker-1",
            token=LeaseToken("token-1"),
            acquired_at=ACQUIRED,
            heartbeat_at=HEARTBEAT,
            expires_at=HEARTBEAT,
        )


def test_lease_renewal_rejects_non_future_expiry() -> None:
    lease = Lease(
        owner="worker-1",
        token=LeaseToken("token-1"),
        acquired_at=ACQUIRED,
        heartbeat_at=ACQUIRED,
        expires_at=EXPIRY,
    )
    with pytest.raises(ValueError, match="expires_at must be after now"):
        lease.renew(
            owner="worker-1",
            token=LeaseToken("token-1"),
            now=HEARTBEAT,
            expires_at=HEARTBEAT,
        )
