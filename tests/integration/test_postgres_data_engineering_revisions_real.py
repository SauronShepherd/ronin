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
    for project, pipeline in ((f"project-a-{suffix}", "main"), (f"project-b-{suffix}", "other")):
        store.save(
            project_id=project,
            pipeline_id=pipeline,
            source_digest="source-digest",
            project_artifact_ref=f"artifact://sha256/{'a' * 64}",
            pipeline_artifacts={"node": f"artifact://sha256/{'b' * 64}"},
            metadata_artifact_ref=f"artifact://sha256/{'c' * 64}",
        )

    references = discover_data_engineering_artifact_references(store)

    assert references == {"data_engineering_revisions": ("a" * 64, "b" * 64, "c" * 64)}
