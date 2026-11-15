from __future__ import annotations

import copy

from tools.ronin_daily_progress import load_ledger, render_report, validate_ledger


def test_daily_progress_ledger_is_consistent() -> None:
    ledger = load_ledger()

    assert validate_ledger(ledger) == []


def test_qualified_family_requires_candidate_bound_evidence() -> None:
    ledger = copy.deepcopy(load_ledger())
    ledger["families"][0]["qualification"] = "qualified"
    ledger["families"][0]["receipt"] = None
    ledger["families"][0]["candidate_sha"] = None

    errors = validate_ledger(ledger)

    assert "P1: qualified family needs a receipt" in errors
    assert "P1: qualified family needs candidate_sha" in errors


def test_report_keeps_family_and_day_progress_separate() -> None:
    report = render_report(load_ledger())

    assert "Families: 1/13 (7.69%)" in report
    assert "Days: 10/39 (25.64%)" in report
    assert "Release gates: 0/10 (0.00%)" in report
    assert "Implementation tasks: not baselined" in report
