from __future__ import annotations

import pytest
from studio_migration import (
    discover_databricks,
    discover_dataiku,
    discover_fabric,
    discover_foundry,
)


def test_named_profiles_emit_distinct_canonical_platform_identity() -> None:
    source = '{"objects":[{"type":"pipeline","id":"p-1"}]}'
    reports = (
        discover_databricks(source, source_version="15"),
        discover_fabric(source, source_version="2026"),
        discover_dataiku(source, source_version="14"),
        discover_foundry(source, source_version="1"),
    )
    assert tuple(report.source_platform for report in reports) == (
        "databricks",
        "microsoft-fabric",
        "dataiku-dss",
        "palantir-foundry-aip",
    )
    assert all(report.objects[0].status == "unsupported" for report in reports)


def test_profiles_normalize_common_vendor_collections() -> None:
    report = discover_databricks('{"resources":{"jobs":[{"id":"job-1"}]}}')
    assert report.objects[0].source_id == "job-1"
    report = discover_fabric('{"items":[{"id":"item-1"}],"pipelines":[{"name":"pipe-1"}]}')
    assert {item.source_id for item in report.objects} == {"item-1", "pipe-1"}


def test_profiles_fail_closed_when_source_identity_is_missing() -> None:
    with pytest.raises(ValueError, match="no explicit identity"):
        discover_dataiku('{"datasets":[{"schema":"secret-free metadata"}]}')
