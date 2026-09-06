"""Canonical UTC instants for the durable lifecycle.

The durable domain orders timestamps for claim eligibility, lease expiry, and
recovery. Lexical ordering is therefore safe only when every value has exactly
one representation. Ronin accepts one canonical form and rejects everything
else instead of normalizing ambiguous boundary input:

    YYYY-MM-DDTHH:MM:SS.ffffffZ
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_CANONICAL = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})\.(\d{6})Z$"
)
_MONTH_DAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


def _is_leap_year(year: int) -> bool:
    return year % 400 == 0 or (year % 4 == 0 and year % 100 != 0)


def _assert_calendar_valid(match: re.Match[str]) -> None:
    year, month, day, hour, minute, second, _microsecond = (
        int(part) for part in match.groups()
    )
    if year < 1:
        raise ValueError("instant year must be between 0001 and 9999")
    if not 1 <= month <= 12:
        raise ValueError("instant month is out of range")
    max_day = _MONTH_DAYS[month - 1] + (1 if month == 2 and _is_leap_year(year) else 0)
    if not 1 <= day <= max_day:
        raise ValueError("instant day is out of range")
    if not 0 <= hour <= 23:
        raise ValueError("instant hour is out of range")
    if not 0 <= minute <= 59:
        raise ValueError("instant minute is out of range")
    if not 0 <= second <= 59:
        raise ValueError("instant second is out of range")


@dataclass(frozen=True, slots=True, order=True)
class Instant:
    """One canonical, totally ordered UTC instant."""

    value: str

    def __post_init__(self) -> None:
        match = _CANONICAL.fullmatch(self.value)
        if match is None:
            raise ValueError(
                "instant must be canonical RFC 3339 UTC: YYYY-MM-DDTHH:MM:SS.ffffffZ"
            )
        _assert_calendar_valid(match)

    def __str__(self) -> str:
        return self.value


__all__ = ("Instant",)
