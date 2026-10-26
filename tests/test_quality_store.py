from __future__ import annotations

from pathlib import Path

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
from studio_quality import evaluate_contract
from studio_storage import (
    CatalogAssetNotFound,
    DataContractConflict,
    QualityRunConflict,
    SqliteCatalogStore,
    SqliteQualityStore,
    SqliteWorkspaceStore,
    WorkspaceNotFound,
    migrate_quality,
    quality_schema_version,
)
from studio_storage.quality import _QUALITY_SCHEMA_VERSION
from studio_storage.sqlite import open_database

_NOW = Instant("2026-10-25T10:00:00.000000Z")
_WORKSPACE = WorkspaceId("quality-store-workspace")
_ASSET = CatalogAsset(AssetId("orders"), "table", "Orders")
_REF = AssetRef(_ASSET.id, AssetVersion("v1"))


def _contract(ref: AssetRef = _REF, *, freshness: int | None = None) -> DataContract:
    return DataContract(
        ref,
        "exact",
        (QualityRule(QualityRuleId("rows"), "row_count", "Rows", parameters=(("min", "1"),)),),
        freshness_seconds=freshness,
    )


def _store(path: Path) -> SqliteQualityStore:
    workspace_store = SqliteWorkspaceStore(path, migration_now=_NOW)
    workspace_store.create_workspace(Workspace(_WORKSPACE, "Quality store"), now=_NOW)
    catalog = SqliteCatalogStore(path, migration_now=_NOW)
    catalog.create_asset(_WORKSPACE, _ASSET, now=_NOW)
    catalog.put_revision(_WORKSPACE, AssetRevision(_REF), now=_NOW)
    return SqliteQualityStore(path, migration_now=_NOW)


def test_quality_migration_is_idempotent_and_rejects_newer_schema(tmp_path: Path) -> None:
    database = tmp_path / "quality.sqlite3"
    _store(database)
    connection = open_database(database)
    try:
        assert quality_schema_version(connection) == _QUALITY_SCHEMA_VERSION
        migrate_quality(connection, now=_NOW)
        assert quality_schema_version(connection) == _QUALITY_SCHEMA_VERSION
        connection.execute(
            "INSERT INTO quality_schema_migrations(version, applied_at) VALUES (?, ?)",
            (_QUALITY_SCHEMA_VERSION + 1, str(_NOW)),
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(RuntimeError, match="newer than supported"):
        SqliteQualityStore(database, migration_now=_NOW)


def test_contracts_round_trip_update_and_list_in_stable_asset_order(tmp_path: Path) -> None:
    store = _store(tmp_path / "quality.sqlite3")
    contract = _contract()
    assert store.put_contract(_WORKSPACE, contract, now=_NOW) == contract
    assert store.put_contract(_WORKSPACE, contract, now=_NOW) == contract

    revised = _contract(freshness=3600)
    assert store.put_contract(_WORKSPACE, revised, now="2026-10-25T10:01:00.000000Z") == revised
    second_ref = AssetRef(_ASSET.id, AssetVersion("v2"))
    catalog = SqliteCatalogStore(tmp_path / "quality.sqlite3", migration_now=_NOW)
    catalog.put_revision(_WORKSPACE, AssetRevision(second_ref), now=_NOW)
    second = _contract(second_ref)
    assert store.put_contracts(_WORKSPACE, (second,), now=_NOW) == (second,)

    assert store.get_contract(_WORKSPACE, _REF) == revised
    assert store.get_contract(_WORKSPACE, second_ref) == second
    assert store.get_contract(_WORKSPACE, AssetRef(_ASSET.id, AssetVersion("missing"))) is None
    assert store.list_contracts(_WORKSPACE) == (revised, second)


def test_contract_batch_rolls_back_and_rejects_inactive_or_missing_scope(tmp_path: Path) -> None:
    database = tmp_path / "quality.sqlite3"
    store = _store(database)
    missing_revision = AssetRef(_ASSET.id, AssetVersion("missing"))
    with pytest.raises(CatalogAssetNotFound):
        store.put_contracts(
            _WORKSPACE,
            (_contract(), _contract(missing_revision)),
            now=_NOW,
        )
    assert store.get_contract(_WORKSPACE, _REF) is None

    with pytest.raises(WorkspaceNotFound):
        store.put_contract(WorkspaceId("missing-workspace"), _contract(), now=_NOW)

    workspace_store = SqliteWorkspaceStore(database, migration_now=_NOW)
    workspace_store.update_workspace(
        Workspace(_WORKSPACE, "Quality store", state="archived"), now=_NOW
    )
    with pytest.raises(DataContractConflict, match="archived workspace"):
        store.put_contract(_WORKSPACE, _contract(), now=_NOW)


def test_quality_runs_are_durable_idempotent_scoped_and_ordered(tmp_path: Path) -> None:
    store = _store(tmp_path / "quality.sqlite3")
    contract = _contract()
    older = evaluate_contract(contract, ({"id": 1},), run_id=QualityRunId("z-older"))
    newer = evaluate_contract(contract, ({"id": 2},), run_id=QualityRunId("a-newer"))

    assert store.record_run(_WORKSPACE, older, now="2026-10-25T10:00:00.000000Z") == older
    assert store.record_run(_WORKSPACE, older, now="2026-10-25T10:05:00.000000Z") == older
    assert store.record_run(_WORKSPACE, newer, now="2026-10-25T10:01:00.000000Z") == newer
    assert store.get_run(_WORKSPACE, older.id) == older
    assert store.get_run(WorkspaceId("other-workspace"), older.id) is None
    assert store.get_run(_WORKSPACE, QualityRunId("missing")) is None
    assert store.get_run_created_at(_WORKSPACE, older.id) == Instant("2026-10-25T10:00:00.000000Z")
    assert store.get_run_created_at(_WORKSPACE, QualityRunId("missing")) is None
    assert store.list_runs(_WORKSPACE, _REF) == (older, newer)
    assert store.list_runs(WorkspaceId("other-workspace"), _REF) == ()

    conflicting = evaluate_contract(contract, (), run_id=older.id)
    with pytest.raises(QualityRunConflict, match="already exists"):
        store.record_run(_WORKSPACE, conflicting, now="2026-10-25T10:02:00.000000Z")
    assert store.get_run(_WORKSPACE, older.id) == older


def test_record_run_rejects_missing_revision_workspace_and_archived_workspace(
    tmp_path: Path,
) -> None:
    database = tmp_path / "quality.sqlite3"
    store = _store(database)
    run = evaluate_contract(_contract(), ({"id": 1},), run_id=QualityRunId("run"))
    with pytest.raises(WorkspaceNotFound):
        store.record_run(WorkspaceId("missing-workspace"), run, now=_NOW)

    workspace_store = SqliteWorkspaceStore(database, migration_now=_NOW)
    workspace_store.update_workspace(
        Workspace(_WORKSPACE, "Quality store", state="archived"), now=_NOW
    )
    with pytest.raises(DataContractConflict, match="archived workspace"):
        store.record_run(_WORKSPACE, run, now=_NOW)
