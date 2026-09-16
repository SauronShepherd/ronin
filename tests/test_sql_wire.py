from datetime import UTC, date, datetime, time
from decimal import Decimal
from uuid import UUID

import pytest
from studio_sql.wire import sql_wire_value


def test_sql_wire_value_has_stable_cross_language_scalar_forms() -> None:
    assert sql_wire_value(datetime(2026, 9, 16, 12, 30, tzinfo=UTC)) == ("2026-09-16T12:30:00Z")
    assert sql_wire_value(date(2026, 9, 16)) == "2026-09-16"
    assert sql_wire_value(time(12, 30)) == "12:30:00"
    assert sql_wire_value(Decimal("12.3400")) == "12.3400"
    assert sql_wire_value(UUID("12345678-1234-5678-1234-567812345678")) == (
        "12345678-1234-5678-1234-567812345678"
    )
    assert sql_wire_value(b"ronin") == "cm9uaW4="


def test_sql_wire_value_rejects_non_finite_and_unknown_values() -> None:
    with pytest.raises(ValueError, match="non-finite"):
        sql_wire_value(float("inf"))
    with pytest.raises(TypeError, match="unsupported"):
        sql_wire_value(object())
