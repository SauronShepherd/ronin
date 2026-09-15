from __future__ import annotations

import pytest

from studio_migration import discover_databricks, qualify_fixture


def test_qualification_requires_complete_report_and_is_deterministic() -> None:
    source = '{"resources":{"jobs":[{"id":"job-1"}]}}'
    first = qualify_fixture(source, discover_databricks, required_source_ids=("job-1",))
    second = qualify_fixture(source, discover_databricks, required_source_ids=("job-1",))
    assert first == second
    assert first.unsupported_objects == 1


def test_qualification_rejects_omitted_objects() -> None:
    with pytest.raises(ValueError, match="omits source objects"):
        qualify_fixture('{"objects":[]}', discover_databricks, required_source_ids=("job-1",))
