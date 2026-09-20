"""Result validation contracts inspired by Spark comparison strategies.

The core stays dependency-free so reports can be planned and tested without a
Spark runtime. A Spark adapter can later compile the same contract to
``assertSchemaEqual``, ``exceptAll`` and key-based full-outer joins.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Literal

from studio_core.canonical_json import encode as encode_canonical_json

CheckMode = Literal["schema", "counts", "multiset", "keyed"]
ReportLevel = Literal["simple", "full"]
CheckStatus = Literal["pass", "warn", "fail"]


@dataclass(frozen=True, slots=True)
class ValidationCheck:
    check_id: str
    mode: CheckMode
    status: CheckStatus
    message: str
    metrics: tuple[tuple[str, str], ...] = ()
    details: tuple[dict[str, object], ...] = ()


@dataclass(frozen=True, slots=True)
class ValidationReport:
    asset_id: str
    level: ReportLevel
    checks: tuple[ValidationCheck, ...]
    expected_digest: str
    actual_digest: str

    @property
    def status(self) -> CheckStatus:
        statuses = {check.status for check in self.checks}
        return "fail" if "fail" in statuses else "warn" if "warn" in statuses else "pass"

    @property
    def digest(self) -> str:
        payload = {
            "asset_id": self.asset_id,
            "level": self.level,
            "status": self.status,
            "expected_digest": self.expected_digest,
            "actual_digest": self.actual_digest,
            "checks": [
                {
                    "check_id": item.check_id,
                    "mode": item.mode,
                    "status": item.status,
                    "message": item.message,
                    "metrics": list(item.metrics),
                    "details": list(item.details),
                }
                for item in self.checks
            ],
        }
        return hashlib.sha256(encode_canonical_json(payload)).hexdigest()

    def to_payload(self) -> dict[str, object]:
        return {
            "asset_id": self.asset_id,
            "level": self.level,
            "status": self.status,
            "digest": self.digest,
            "expected_digest": self.expected_digest,
            "actual_digest": self.actual_digest,
            "checks": [
                {
                    "check_id": item.check_id,
                    "mode": item.mode,
                    "status": item.status,
                    "message": item.message,
                    "metrics": dict(item.metrics),
                    "details": list(item.details),
                }
                for item in self.checks
            ],
        }

    def to_json(self) -> str:
        return encode_canonical_json(self.to_payload()).decode("utf-8")


def _digest(rows: list[dict[str, object]]) -> str:
    return hashlib.sha256(encode_canonical_json(rows)).hexdigest()


def _schema(rows: list[dict[str, object]]) -> tuple[str, ...]:
    keys: set[str] = set()
    for row in rows:
        keys.update(row)
    return tuple(sorted(keys))


def _equal(left: object, right: object, tolerance: float) -> bool:
    if left is None or right is None:
        return left is right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return math.isclose(float(left), float(right), rel_tol=0.0, abs_tol=tolerance)
    return left == right


def _key(row: dict[str, object], key_columns: tuple[str, ...]) -> tuple[object, ...]:
    return tuple(row.get(column) for column in key_columns)


def validate_results(
    expected: list[dict[str, object]],
    actual: list[dict[str, object]],
    *,
    asset_id: str,
    level: ReportLevel = "simple",
    modes: tuple[CheckMode, ...] = ("schema", "counts", "multiset"),
    key_columns: tuple[str, ...] = (),
    tolerances: dict[str, float] | None = None,
) -> ValidationReport:
    """Validate expected/actual rows and return a compact or forensic report.

    ``multiset`` is duplicate-aware. ``keyed`` refuses to invent pairings for
    duplicate keys and emits payload-level details instead.
    """
    if not asset_id or asset_id != asset_id.strip():
        raise ValueError("asset_id must be non-empty and trimmed")
    if level not in {"simple", "full"}:
        raise ValueError("report level must be simple or full")
    tolerance_map = tolerances or {}
    checks: list[ValidationCheck] = []
    if "schema" in modes:
        left, right = _schema(expected), _schema(actual)
        checks.append(
            ValidationCheck(
                "schema",
                "schema",
                "pass" if left == right else "fail",
                "schemas match" if left == right else "schemas differ",
                (("expected_columns", str(len(left))), ("actual_columns", str(len(right)))),
                (
                    {
                        "missing": sorted(set(left) - set(right)),
                        "unexpected": sorted(set(right) - set(left)),
                    },
                )
                if level == "full"
                else (),
            )
        )
    if "counts" in modes:
        checks.append(
            ValidationCheck(
                "row_count",
                "counts",
                "pass" if len(expected) == len(actual) else "fail",
                "row counts match" if len(expected) == len(actual) else "row counts differ",
                (
                    ("expected", str(len(expected))),
                    ("actual", str(len(actual))),
                    ("delta", str(len(actual) - len(expected))),
                ),
            )
        )
    if "multiset" in modes:
        left = Counter(json.dumps(row, sort_keys=True, default=str) for row in expected)
        right = Counter(json.dumps(row, sort_keys=True, default=str) for row in actual)
        only_expected = sum((left - right).values())
        only_actual = sum((right - left).values())
        details = ()
        if level == "full":
            details = tuple(
                {"side": "expected", "row": json.loads(raw), "count": count}
                for raw, count in sorted((left - right).items())
            ) + tuple(
                {"side": "actual", "row": json.loads(raw), "count": count}
                for raw, count in sorted((right - left).items())
            )
        checks.append(
            ValidationCheck(
                "multiset",
                "multiset",
                "pass" if not only_expected and not only_actual else "fail",
                "duplicate-aware rows match"
                if not only_expected and not only_actual
                else "duplicate-aware rows differ",
                (("expected_only", str(only_expected)), ("actual_only", str(only_actual))),
                details,
            )
        )
    if "keyed" in modes:
        if not key_columns:
            raise ValueError("keyed validation requires key_columns")
        expected_groups: defaultdict[tuple[object, ...], list[dict[str, object]]] = defaultdict(
            list
        )
        actual_groups: defaultdict[tuple[object, ...], list[dict[str, object]]] = defaultdict(list)
        for row in expected:
            expected_groups[_key(row, key_columns)].append(row)
        for row in actual:
            actual_groups[_key(row, key_columns)].append(row)
        details: list[dict[str, object]] = []
        for key in sorted(set(expected_groups) | set(actual_groups), key=str):
            left_rows, right_rows = expected_groups.get(key, []), actual_groups.get(key, [])
            if len(left_rows) != 1 or len(right_rows) != 1:
                if left_rows != right_rows:
                    details.append(
                        {
                            "status": "__PAYLOAD__",
                            "key": list(key),
                            "expected_count": len(left_rows),
                            "actual_count": len(right_rows),
                        }
                    )
                continue
            left_row, right_row = left_rows[0], right_rows[0]
            for column in sorted(set(left_row) | set(right_row)):
                if column in key_columns:
                    continue
                if not _equal(
                    left_row.get(column), right_row.get(column), tolerance_map.get(column, 0.0)
                ):
                    details.append(
                        {
                            "status": "<>",
                            "key": list(key),
                            "column": column,
                            "expected": left_row.get(column),
                            "actual": right_row.get(column),
                        }
                    )
        if level == "simple":
            details = details[:20]
        checks.append(
            ValidationCheck(
                "keyed",
                "keyed",
                "pass" if not details else "fail",
                "keyed values match" if not details else "keyed values differ",
                (("keys", str(len(expected_groups))), ("differences", str(len(details)))),
                tuple(details) if level == "full" else tuple(details[:20]),
            )
        )
    return ValidationReport(asset_id, level, tuple(checks), _digest(expected), _digest(actual))


__all__ = ("ValidationCheck", "ValidationReport", "validate_results")
