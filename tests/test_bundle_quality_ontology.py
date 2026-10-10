from __future__ import annotations

from pathlib import Path

from studio_core import (
    AssetId,
    AssetRef,
    AssetVersion,
    DataContract,
    ObjectType,
    OntologyDefinition,
    OntologyId,
    PropertyDefinition,
    QualityRule,
    QualityRuleId,
    WorkspaceId,
)
from studio_execution.bundle_ontology import export_ontology_bundle, import_ontology_bundle
from studio_quality import (
    commit_quality_bundle_import,
    export_quality_bundle,
    plan_quality_bundle_import,
)
from studio_orchestrator import Instant
from studio_storage.bundle import verify_bundle

_WORKSPACE = WorkspaceId("workspace-bundle")
_NOW = Instant("2026-10-10T00:00:00.000000Z")


def _contract() -> DataContract:
    return DataContract(
        AssetRef(AssetId("orders"), AssetVersion("1")),
        "exact",
        (QualityRule(QualityRuleId("not-null"), "null", "order id", field="id"),),
    )


def _ontology() -> OntologyDefinition:
    return OntologyDefinition(
        OntologyId("commerce"),
        "1",
        "Commerce",
        (
            ObjectType(
                "Order",
                AssetRef(AssetId("orders"), AssetVersion("1")),
                ("id",),
                (PropertyDefinition("id", "string", "id", True),),
            ),
        ),
    )


class _QualityStore:
    def __init__(self, contracts: tuple[DataContract, ...] = ()) -> None:
        self.contracts = list(contracts)

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


class _OntologyStore:
    def __init__(self, values: tuple[OntologyDefinition, ...] = ()) -> None:
        self.values = list(values)

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


def test_quality_bundle_round_trip_preserves_contract_identity(tmp_path: Path) -> None:
    source = _QualityStore((_contract(),))
    bundle = tmp_path / "quality.roninbundle"
    export_quality_bundle(_WORKSPACE, source, bundle)

    plan = plan_quality_bundle_import(bundle)
    target = _QualityStore()
    imported = commit_quality_bundle_import(bundle, _WORKSPACE, target, now=_NOW)

    assert imported.contracts == plan.contracts
    assert target.contracts == [_contract()]
    verify_bundle(bundle)


def test_ontology_bundle_round_trip_preserves_definition_identity(tmp_path: Path) -> None:
    source = _OntologyStore((_ontology(),))
    bundle = tmp_path / "ontology.roninbundle"
    export_ontology_bundle(_WORKSPACE, source, bundle)

    target = _OntologyStore()
    imported = import_ontology_bundle(bundle, _WORKSPACE, target, now=_NOW)

    assert imported == (_ontology(),)
    assert target.values == [_ontology()]
    verify_bundle(bundle)
