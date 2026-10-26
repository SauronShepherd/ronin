from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from studio_core import (
    AssetId,
    AssetRef,
    AssetRevision,
    AssetVersion,
    CatalogAsset,
    DataContract,
    QualityRule,
    QualityRuleId,
    QualityRunId,
    Workspace,
    WorkspaceId,
)
from studio_orchestrator import Instant
from studio_quality import evaluate_contract, execute_quality
from studio_storage import PostgresMetadataStore, PostgresQualityStore, QualityRunConflict

_DSN = os.environ.get("RONIN_TEST_POSTGRES_DSN")
if not _DSN:
    pytest.skip("RONIN_TEST_POSTGRES_DSN is not configured", allow_module_level=True)

psycopg = pytest.importorskip("psycopg")


def test_postgres_quality_store_is_durable_scoped_and_chronological() -> None:
    suffix = uuid4().hex
    workspace = Workspace(WorkspaceId(f"quality-{suffix}"), f"Quality {suffix}")
    asset = CatalogAsset(AssetId("orders"), "table", "Orders")
    ref = AssetRef(asset.id, AssetVersion("1"))
    contract = DataContract(
        ref,
        "exact",
        (
            QualityRule(
                QualityRuleId("non-empty"),
                "row_count",
                "At least one order",
                blocking=True,
                parameters=(("min", "1"),),
            ),
        ),
    )
    metadata = PostgresMetadataStore(_DSN, application_name="ronin-postgres-quality-test")
    store = PostgresQualityStore(metadata)
    metadata.create_workspace(workspace, now=Instant("2026-10-24T00:00:00.000000Z"))
    metadata.create_asset(workspace.id, asset, now=Instant("2026-10-24T00:00:00.000000Z"))
    metadata.put_revision(
        workspace.id,
        AssetRevision(ref, schema_digest="orders-v1"),
        now=Instant("2026-10-24T00:00:00.000000Z"),
    )

    try:
        assert (
            store.put_contract(workspace.id, contract, now="2026-10-24T00:00:00.000000Z")
            == contract
        )
        assert (
            store.put_contract(workspace.id, contract, now="2026-10-24T00:01:00.000000Z")
            == contract
        )
        updated_contract = DataContract(
            ref,
            "exact",
            contract.rules,
            freshness_seconds=3600,
        )
        assert (
            store.put_contract(workspace.id, updated_contract, now="2026-10-24T00:01:30.000000Z")
            == updated_contract
        )
        assert store.get_contract(workspace.id, ref) == updated_contract
        assert store.list_contracts(workspace.id) == (updated_contract,)
        contract = updated_contract

        first = execute_quality(
            store,
            workspace.id,
            ref,
            [{"id": 1}],
            run_id=QualityRunId("z-first"),
            now="2026-10-24T00:02:00.000000Z",
        )
        assert store.record_run(workspace.id, first, now="2026-10-24T00:02:00.000000Z") == first
        second = execute_quality(
            store,
            workspace.id,
            ref,
            [{"id": 2}],
            run_id=QualityRunId("a-second"),
            now="2026-10-24T00:03:00.000000Z",
        )
        assert store.get_run(workspace.id, first.id) == first
        assert store.list_runs(workspace.id, ref) == (first, second)

        concurrent = evaluate_contract(contract, [{"id": 3}], run_id=QualityRunId("concurrent"))
        with ThreadPoolExecutor(max_workers=4) as executor:
            replays = tuple(
                executor.map(
                    lambda _: store.record_run(
                        workspace.id, concurrent, now="2026-10-24T00:03:30.000000Z"
                    ),
                    range(8),
                )
            )
        assert replays == (concurrent,) * 8
        assert store.list_runs(workspace.id, ref) == (first, second, concurrent)

        conflicting = evaluate_contract(
            contract,
            [],
            run_id=first.id,
        )
        with pytest.raises(QualityRunConflict):
            store.record_run(workspace.id, conflicting, now="2026-10-24T00:04:00.000000Z")
        assert store.get_contract(WorkspaceId(f"other-{suffix}"), ref) is None
    finally:
        with psycopg.connect(_DSN, autocommit=True) as connection, connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM ronin_workspaces WHERE workspace_id=%s", (str(workspace.id),)
            )
