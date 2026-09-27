from studio_migration import validate_results


def test_simple_report_catches_duplicate_aware_row_differences() -> None:
    report = validate_results(
        [{"id": 1, "amount": 10}, {"id": 1, "amount": 10}],
        [{"id": 1, "amount": 10}],
        asset_id="orders",
    )
    assert report.status == "fail"
    assert report.to_payload()["level"] == "simple"
    assert any(item.check_id == "multiset" for item in report.checks)


def test_full_keyed_report_explains_changed_cells_and_tolerance() -> None:
    report = validate_results(
        [{"id": "a", "amount": 10.00, "status": 1}, {"id": "b", "amount": 4.0, "status": 1}],
        [{"id": "a", "amount": 10.005, "status": 9}, {"id": "b", "amount": 4.0, "status": 1}],
        asset_id="orders",
        level="full",
        modes=("schema", "counts", "keyed"),
        key_columns=("id",),
        tolerances={"amount": 0.01},
    )
    assert report.status == "fail"
    keyed = next(item for item in report.checks if item.check_id == "keyed")
    assert len(keyed.details) == 1
    assert keyed.details[0]["column"] == "status"


def test_keyed_duplicate_keys_use_payload_status_instead_of_fake_pairing() -> None:
    report = validate_results(
        [{"id": "a", "value": 1}, {"id": "a", "value": 2}],
        [{"id": "a", "value": 1}, {"id": "a", "value": 3}],
        asset_id="events",
        level="full",
        modes=("keyed",),
        key_columns=("id",),
    )
    detail = report.checks[0].details[0]
    assert detail["status"] == "__PAYLOAD__"
