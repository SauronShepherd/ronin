from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st
from studio_orchestrator import Instant
from studio_storage.memory import _add_seconds as memory_add_seconds
from studio_storage.sqlite import _add_seconds as sqlite_add_seconds

_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


def _canonical(value: datetime) -> str:
    return value.astimezone(UTC).strftime(_FORMAT)


@pytest.mark.parametrize(
    "value",
    [
        "0001-01-01T00:00:00.000000Z",
        "2000-02-29T23:59:59.999999Z",
        "2024-02-29T12:34:56.123456Z",
        "2100-02-28T12:34:56.123456Z",
        "9999-12-31T23:59:59.999999Z",
    ],
)
def test_instant_accepts_only_calendar_valid_canonical_values(value: str) -> None:
    instant = Instant(value)
    assert str(instant) == value
    assert instant.value == value


@pytest.mark.parametrize(
    "value",
    [
        "",
        "2026-09-06T09:00:00Z",
        "2026-09-06T09:00:00.000Z",
        "2026-09-06T09:00:00.000000+00:00",
        "2026-09-06T11:00:00.000000+02:00",
        "2026-09-06T09:00:00.000000",
        "0000-01-01T00:00:00.000000Z",
        "2026-00-01T00:00:00.000000Z",
        "2026-13-01T00:00:00.000000Z",
        "2026-01-00T00:00:00.000000Z",
        "2026-01-32T00:00:00.000000Z",
        "2100-02-29T00:00:00.000000Z",
        "2026-01-01T24:00:00.000000Z",
        "2026-01-01T00:60:00.000000Z",
        "2026-01-01T00:00:60.000000Z",
    ],
)
def test_instant_rejects_noncanonical_or_invalid_values(value: str) -> None:
    with pytest.raises(ValueError, match="instant"):
        Instant(value)


_UTC_DATETIMES = st.datetimes(
    min_value=datetime(2000, 1, 1),
    max_value=datetime(2099, 12, 31, 23, 59, 59, 999999),
    timezones=st.just(UTC),
)


@given(_UTC_DATETIMES, _UTC_DATETIMES)
def test_lexical_order_equals_chronological_order(a: datetime, b: datetime) -> None:
    left = Instant(_canonical(a))
    right = Instant(_canonical(b))
    assert (left < right) == (a < b)
    assert (left <= right) == (a <= b)
    assert (left == right) == (a == b)


@given(_UTC_DATETIMES, st.integers(min_value=-86400, max_value=86400))
def test_store_add_seconds_round_trips(base: datetime, delta: int) -> None:
    # Keep generated values away from datetime's finite edges.
    canonical = Instant(_canonical(base))
    expected = base + timedelta(seconds=delta)
    expected_text = Instant(_canonical(expected))
    assert memory_add_seconds(canonical, delta) == expected_text
    assert sqlite_add_seconds(canonical, delta) == expected_text
