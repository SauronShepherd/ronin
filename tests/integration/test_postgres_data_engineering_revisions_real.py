from __future__ import annotations

import os
from uuid import uuid4

import pytest
from studio_data_engineering import PostgresRevisionStore
from studio_storage import discover_data_engineering_artifact_references

pytestmark = pytest.mark.skipif(
    not os.environ.get("RONIN_POSTGRES_TEST_DSN"),
    reason="real PostgreSQL qualification requires RONIN_POSTGRES_TEST_DSN",
)


def test_postgres_revision_inventory_discovers_all_project_artifacts() -> None:
    store = PostgresRevisionStore(
        os.environ["RONIN_POSTGRES_TEST_DSN"],
        application_name="ronin-data-engineering-qualification",
    )
    suffix = uuid4().hex
    project_a = f"project-a-{suffix}"
    project_b = f"project-b-{suffix}"
    store.save(
        project_id=project_a,
        pipeline_id="main",
        source_digest="source-digest",
        project_artifact_ref=f"artifact://sha256/{'a' * 64}",
        pipeline_artifacts={"node": f"artifact://sha256/{'b' * 64}"},
        metadata_artifact_ref=f"artifact://sha256/{'c' * 64}",
    )
    store.save(
        project_id=project_a,
        pipeline_id="main",
        source_digest="source-digest-2",
        project_artifact_ref=f"artifact://sha256/{'d' * 64}",
        pipeline_artifacts={"node": f"artifact://sha256/{'e' * 64}"},
        metadata_artifact_ref=f"artifact://sha256/{'f' * 64}",
        expected_revision=1,
    )
    store.save(
        project_id=project_b,
        pipeline_id="other",
        source_digest="source-digest",
        project_artifact_ref=f"artifact://sha256/{'a' * 64}",
        pipeline_artifacts={"node": f"artifact://sha256/{'b' * 64}"},
        metadata_artifact_ref=f"artifact://sha256/{'c' * 64}",
    )

    references = discover_data_engineering_artifact_references(store)
    revisions = [
        record
        for record in store.list_all_revisions()
        if record["project_id"] == project_a and record["pipeline_id"] == "main"
    ]

    assert references == {"data_engineering_revisions": tuple(char * 64 for char in "abcdef")}
    assert {record["revision"] for record in revisions} == {1, 2}
