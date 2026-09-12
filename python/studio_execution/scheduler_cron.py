"""Strict five-field cron evaluation for durable Ronin schedules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from studio_orchestrator import Instant
from studio_storage.scheduler import Schedule


class CronSyntaxError(ValueError):
    """Raised when a schedule cron expression is outside the supported grammar."""


@dataclass(frozen=True, slots=True)
class _CronField:
    values: frozenset[int]
    wildcard: bool


def _parse_integer(value: str, *, minimum: int, maximum: int, field: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise CronSyntaxError(f"{field} contains a non-integer value") from exc
    if not minimum <= parsed <= maximum:
        raise CronSyntaxError(f"{field} value is outside {minimum}..{maximum}")
    return parsed


def _parse_field(
    value: str,
    *,
    minimum: int,
    maximum: int,
    field: str,
    sunday_seven: bool = False,
) -> _CronField:
    if not value or value != value.strip():
        raise CronSyntaxError(f"{field} must be non-empty and trimmed")
    wildcard = value == "*"
    result: set[int] = set()
    input_maximum = 7 if sunday_seven else maximum
    for item in value.split(","):
        if not item:
            raise CronSyntaxError(f"{field} contains an empty list item")
        base, separator, step_text = item.partition("/")
        step = 1
        if separator:
            if "/" in step_text or not step_text:
                raise CronSyntaxError(f"{field} contains an invalid step")
            step = _parse_integer(
                step_text,
                minimum=1,
                maximum=input_maximum - minimum + 1,
                field=f"{field} step",
            )
        if base == "*":
            start, end = minimum, input_maximum
        elif "-" in base:
            pieces = base.split("-")
            if len(pieces) != 2:
                raise CronSyntaxError(f"{field} contains an invalid range")
            start = _parse_integer(
                pieces[0], minimum=minimum, maximum=input_maximum, field=field
            )
            end = _parse_integer(
                pieces[1], minimum=minimum, maximum=input_maximum, field=field
            )
            if end < start:
                raise CronSyntaxError(f"{field} ranges must be ascending")
        else:
            if separator:
                raise CronSyntaxError(f"{field} steps require '*' or a range")
            single = _parse_integer(
                base, minimum=minimum, maximum=input_maximum, field=field
            )
            start, end = single, single
        for candidate in range(start, end + 1, step):
            result.add(0 if sunday_seven and candidate == 7 else candidate)
    if not result:
        raise CronSyntaxError(f"{field} selects no values")
    return _CronField(frozenset(result), wildcard)


@dataclass(frozen=True, slots=True)
class CronExpression:
    minute: _CronField
    hour: _CronField
    day_of_month: _CronField
    month: _CronField
    day_of_week: _CronField

    @classmethod
    def parse(cls, expression: str) -> CronExpression:
        parts = expression.split()
        if len(parts) != 5:
            raise CronSyntaxError("cron expression must contain exactly five fields")
        return cls(
            _parse_field(parts[0], minimum=0, maximum=59, field="minute"),
            _parse_field(parts[1], minimum=0, maximum=23, field="hour"),
            _parse_field(parts[2], minimum=1, maximum=31, field="day of month"),
            _parse_field(parts[3], minimum=1, maximum=12, field="month"),
            _parse_field(
                parts[4],
                minimum=0,
                maximum=6,
                field="day of week",
                sunday_seven=True,
            ),
        )

    def matches_local(self, value: datetime) -> bool:
        if value.tzinfo is None:
            raise ValueError("cron matching requires an aware datetime")
        if value.minute not in self.minute.values or value.hour not in self.hour.values:
            return False
        if value.month not in self.month.values:
            return False
        day_of_month_matches = value.day in self.day_of_month.values
        cron_day_of_week = (value.weekday() + 1) % 7
        day_of_week_matches = cron_day_of_week in self.day_of_week.values
        if self.day_of_month.wildcard and self.day_of_week.wildcard:
            return True
        if self.day_of_month.wildcard:
            return day_of_week_matches
        if self.day_of_week.wildcard:
            return day_of_month_matches
        # POSIX/Vixie-style cron treats day-of-month and day-of-week as OR when
        # both are explicitly restricted.
        return day_of_month_matches or day_of_week_matches


def _instant_datetime(value: Instant | str) -> datetime:
    instant = Instant(value)
    return datetime.strptime(str(instant), "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)


def _minute_instant(value: datetime) -> Instant:
    canonical = value.astimezone(UTC).replace(second=0, microsecond=0)
    return Instant(canonical.strftime("%Y-%m-%dT%H:%M:%S.%fZ"))


def schedule_matches(schedule: Schedule, instant: Instant | str) -> bool:
    """Evaluate one UTC instant against a schedule's local cron semantics."""

    if not schedule.enabled:
        return False
    try:
        timezone = ZoneInfo(schedule.timezone)
    except ZoneInfoNotFoundError as exc:
        raise CronSyntaxError(f"unknown schedule timezone: {schedule.timezone}") from exc
    expression = CronExpression.parse(schedule.cron)
    local = _instant_datetime(instant).astimezone(timezone)
    return expression.matches_local(local)


def evaluated_minutes(
    *,
    cursor: Instant | None,
    through: Instant | str,
    max_scan_minutes: int,
) -> tuple[Instant, ...]:
    """Return UTC minute instants after cursor through the requested time.

    A schedule without a cursor starts at the current minute only. Existing
    cursors catch up every missed minute. Large gaps fail rather than silently
    skipping schedule fires.
    """

    if max_scan_minutes < 1:
        raise ValueError("max_scan_minutes must be positive")
    end = _minute_instant(_instant_datetime(through))
    end_dt = _instant_datetime(end)
    if cursor is None:
        start_dt = end_dt - timedelta(minutes=1)
    else:
        cursor_dt = _instant_datetime(cursor)
        if cursor_dt.second != 0 or cursor_dt.microsecond != 0:
            raise ValueError("schedule cursor must be aligned to a UTC minute")
        if cursor_dt >= end_dt:
            return ()
        start_dt = cursor_dt
    gap_minutes = int((end_dt - start_dt).total_seconds() // 60)
    if gap_minutes > max_scan_minutes:
        raise RuntimeError(
            f"schedule catch-up requires {gap_minutes} minutes, exceeding limit "
            f"{max_scan_minutes}"
        )
    return tuple(
        _minute_instant(start_dt + timedelta(minutes=offset))
        for offset in range(1, gap_minutes + 1)
    )


__all__ = (
    "CronExpression",
    "CronSyntaxError",
    "evaluated_minutes",
    "schedule_matches",
)
