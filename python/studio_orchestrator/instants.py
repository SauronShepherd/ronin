"""Canonical UTC instants for the durable lifecycle.

The durable domain orders timestamps for claim eligibility, lease expiry, and
recovery. Lexical ordering is therefore safe only when every value has exactly
one representation. Ronin accepts one canonical form and rejects everything
else instead of normalizing ambiguous boundary input:

    YYYY-MM-DDTHH:MM:SS.ffffffZ
"""

from __future__ import annotations

import re

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


class Instant(str):
    """One canonical, totally ordered UTC instant.

    ``Instant`` subclasses ``str`` deliberately: SQLite persists lifecycle
    instants as TEXT, and the one canonical representation makes lexical order
    identical to chronological order without adapter-specific encodings.
    """

    def __new__(cls, value: str) -> Instant:
        match = _CANONICAL.fullmatch(value)
        if match is None:
            raise ValueError(
                "instant must be canonical RFC 3339 UTC: YYYY-MM-DDTHH:MM:SS.ffffffZ"
            )
        _assert_calendar_valid(match)
        return str.__new__(cls, value)

    @property
    def value(self) -> str:
        return str(self)


__all__ = ("Instant",)
