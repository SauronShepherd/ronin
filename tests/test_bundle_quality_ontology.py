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
    ObjectType,
    OntologyDefinition,
    OntologyId,
    PropertyDefinition,
    QualityRule,
    QualityRuleId,
    Workspace,
    WorkspaceId,
)
from studio_core.bundle_inventory import BUNDLE_INVENTORY_PATH
from studio_execution.bundle_ontology import export_ontology_bundle, import_ontology_bundle
from studio_orchestrator import Instant
from studio_quality import (
    commit_quality_bundle_import,
    export_quality_bundle,
    plan_quality_bundle_import,
)
from studio_storage.bundle import verify_bundle
from studio_storage.catalog import CatalogAssetNotFound, SqliteCatalogStore
from studio_storage.ontology import OntologyConflict, SqliteOntologyStore
from studio_storage.workspaces import SqliteWorkspaceStore

_WORKSPACE = WorkspaceId("workspace-bundle")
_NOW = Instant("2026-10-10T00:00:00.000000Z")


def _contract() -> DataContract:
    return DataContract(
        AssetRef(AssetId("orders"), AssetVersion("1")),
        "exact",
        (QualityRule(QualityRuleId("not-null"), "null", "order id", field="id"),),
    )


def _ontology(
    ontology_id: str = "commerce",
    name: str = "Commerce",
    asset_id: str = "orders",
) -> OntologyDefinition:
    return OntologyDefinition(
        OntologyId(ontology_id),
        "1",
        name,
        (
            ObjectType(
                "Order",
                AssetRef(AssetId(asset_id), AssetVersion("1")),
                ("id",),
                (PropertyDefinition("id", "string", "id", True),),
            ),
        ),
    )


class _QualityStore:
    def __init__(self, contracts: tuple[DataContract, ...] = ()) -> None:
        self.contracts = list(contracts)
        self.batch_calls = 0

    def list_contracts(self, workspace_id: WorkspaceId) -> tuple[DataContract, ...]:
        assert workspace_id == _WORKSPACE
        return tuple(self.contracts)

    def put_contract(
        self, workspace_id: WorkspaceId, contract: DataContract, *, now: Instant | str
    ) -> DataContract:
        assert workspace_id == _WORKSPACE
        assert Instant(now) == _NOW
        self.contracts.append(contract)
        return contract

    def put_contracts(
        self,
        workspace_id: WorkspaceId,
        contracts: tuple[DataContract, ...],
        *,
        now: Instant | str,
    ) -> tuple[DataContract, ...]:
        self.batch_calls += 1
        for contract in contracts:
            self.put_contract(workspace_id, contract, now=now)
        return contracts


class _OntologyStore:
    def __init__(self, values: tuple[OntologyDefinition, ...] = ()) -> None:
        self.values = list(values)
        self.batch_calls = 0

    def list_all(self, workspace_id: WorkspaceId) -> tuple[OntologyDefinition, ...]:
        assert workspace_id == _WORKSPACE
        return tuple(self.values)

    def put(
        self, workspace_id: WorkspaceId, ontology: OntologyDefinition, *, now: Instant | str
    ) -> OntologyDefinition:
        assert workspace_id == _WORKSPACE
        assert Instant(now) == _NOW
        self.values.append(ontology)
        return ontology

    def put_many(
        self,
        workspace_id: WorkspaceId,
        ontologies: tuple[OntologyDefinition, ...],
        *,
        now: Instant | str,
    ) -> tuple[OntologyDefinition, ...]:
        assert workspace_id == _WORKSPACE
        assert Instant(now) == _NOW
        self.batch_calls += 1
        values = list(self.values)
        for ontology in ontologies:
            existing = next(
                (
                    item
                    for item in values
                    if item.id == ontology.id and item.version == ontology.version
                ),
                None,
            )
            if existing is not None and existing != ontology:
                raise ValueError("ontology definition conflict")
            if existing is None:
                values.append(ontology)
        self.values = values
        return ontologies


def _sqlite_ontology_store(
    path: Path, *, asset_ids: tuple[str, ...] = ("orders",)
) -> SqliteOntologyStore:
    workspaces = SqliteWorkspaceStore(path, migration_now=_NOW)
    workspaces.create_workspace(Workspace(_WORKSPACE, "Bundle workspace"), now=_NOW)
    catalog = SqliteCatalogStore(path, migration_now=_NOW)
    for asset_id in asset_ids:
        ref = AssetRef(AssetId(asset_id), AssetVersion("1"))
        catalog.create_asset(
            _WORKSPACE,
            CatalogAsset(ref.asset_id, "table", asset_id),
            now=_NOW,
        )
        catalog.put_revision(_WORKSPACE, AssetRevision(ref), now=_NOW)
    return SqliteOntologyStore(path, migration_now=_NOW)


def test_quality_bundle_round_trip_preserves_contract_identity(tmp_path: Path) -> None:
    source = _QualityStore((_contract(),))
    bundle = tmp_path / "quality.roninbundle"
    export_quality_bundle(_WORKSPACE, source, bundle)

    plan = plan_quality_bundle_import(bundle)
    target = _QualityStore()
    imported = commit_quality_bundle_import(bundle, _WORKSPACE, target, now=_NOW)

    assert imported.contracts == plan.contracts
    assert target.contracts == [_contract()]
    assert target.batch_calls == 1
    verify_bundle(bundle)


def test_ontology_bundle_round_trip_preserves_definition_identity(tmp_path: Path) -> None:
    source = _OntologyStore((_ontology(),))
    bundle = tmp_path / "ontology.roninbundle"
    export_ontology_bundle(_WORKSPACE, source, bundle)

    target = _OntologyStore()
    imported = import_ontology_bundle(bundle, _WORKSPACE, target, now=_NOW)

    assert imported == (_ontology(),)
    assert target.values == [_ontology()]
    assert target.batch_calls == 1
    verify_bundle(bundle)


def test_ontology_bundle_import_is_atomic_on_late_missing_asset(tmp_path: Path) -> None:
    source = _OntologyStore((_ontology(), _ontology("shipping", "Shipping", "shipments")))
    bundle = tmp_path / "ontology.roninbundle"
    export_ontology_bundle(_WORKSPACE, source, bundle)
    target = _sqlite_ontology_store(tmp_path / "target.sqlite3")

    with pytest.raises(CatalogAssetNotFound):
        import_ontology_bundle(bundle, _WORKSPACE, target, now=_NOW)

    assert target.list_all(_WORKSPACE) == ()


def test_ontology_bundle_import_is_atomic_on_late_definition_conflict(tmp_path: Path) -> None:
    source = _OntologyStore((_ontology(), _ontology("shipping", "Shipping")))
    bundle = tmp_path / "ontology.roninbundle"
    export_ontology_bundle(_WORKSPACE, source, bundle)
    target = _sqlite_ontology_store(tmp_path / "target.sqlite3")
    existing = _ontology("shipping", "Existing shipping")
    target.put(_WORKSPACE, existing, now=_NOW)

    with pytest.raises(OntologyConflict, match="shipping@1"):
        import_ontology_bundle(bundle, _WORKSPACE, target, now=_NOW)

    assert target.list_all(_WORKSPACE) == (existing,)


def test_ontology_bundle_import_replays_exactly_on_sqlite(tmp_path: Path) -> None:
    values = (_ontology(), _ontology("shipping", "Shipping"))
    source = _OntologyStore(values)
    bundle = tmp_path / "ontology.roninbundle"
    export_ontology_bundle(_WORKSPACE, source, bundle)
    target = _sqlite_ontology_store(tmp_path / "target.sqlite3")

    first = import_ontology_bundle(bundle, _WORKSPACE, target, now=_NOW)
    replay = import_ontology_bundle(bundle, _WORKSPACE, target, now=_NOW)

    assert first == replay == values
    assert target.list_all(_WORKSPACE) == values


def test_ontology_bundle_rejects_inventory_media_type_drift(tmp_path: Path) -> None:
    source = _OntologyStore((_ontology(),))
    bundle = tmp_path / "ontology.roninbundle"
    export_ontology_bundle(_WORKSPACE, source, bundle)

    # The archive remains structurally valid, but the inventory contract is
    # no longer the ontology Bundle contract and must fail closed.
    from studio_storage.bundle import BundleFile, write_bundle
    from studio_storage.bundle_payload import read_bundle_payload

    inventory = read_bundle_payload(bundle, BUNDLE_INVENTORY_PATH)
    replacement = BundleFile(
        BUNDLE_INVENTORY_PATH,
        "application/json",
        inventory.file.data,
    )
    files = [replacement]
    for item in inventory.manifest.entries:
        if item.path != BUNDLE_INVENTORY_PATH:
            payload = read_bundle_payload(bundle, item.path)
            files.append(payload.file)
    write_bundle(bundle, tuple(files))

    import pytest

    with pytest.raises(ValueError, match="unsupported media type"):
        import_ontology_bundle(bundle, _WORKSPACE, _OntologyStore(), now=_NOW)
