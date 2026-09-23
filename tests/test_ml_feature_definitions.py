import pytest
from studio_core import AssetId, AssetRef, AssetVersion
from studio_core import WorkspaceId
from studio_orchestrator import Instant
from studio_ml import (
    FeatureDefinition,
    FeatureDefinitionConflict,
    FeatureDefinitionService,
    FeatureSpec,
)
from studio_ml.sqlite import SqliteMLLabStore


def test_feature_definition_round_trips_with_dataset_snapshot() -> None:
    definition = FeatureDefinition(
        "features/customer",
        "Customer features",
        "project/demo",
        AssetRef(AssetId("table/customers"), AssetVersion("3")),
        (FeatureSpec("age", "numeric"), FeatureSpec("country", "categorical")),
        transform="standardize-v1",
    )
    assert FeatureDefinition.from_payload(definition.to_payload()) == definition


def test_feature_definition_rejects_duplicate_columns() -> None:
    with pytest.raises(ValueError, match="unique"):
        FeatureDefinition(
            "features/customer",
            "Customer features",
            "project/demo",
            AssetRef(AssetId("table/customers"), AssetVersion("1")),
            (FeatureSpec("age"), FeatureSpec("age")),
        )


def test_feature_definition_rejects_boolean_version() -> None:
    with pytest.raises(ValueError, match="schema or version"):
        FeatureDefinition(
            "features/customer",
            "Customer features",
            "project/demo",
            AssetRef(AssetId("table/customers"), AssetVersion("1")),
            (FeatureSpec("age"),),
            version=True,
        )


def test_feature_definition_store_is_project_scoped_and_versioned(tmp_path) -> None:
    store = SqliteMLLabStore(
        tmp_path / "ml.sqlite", migration_now=Instant("2026-09-22T00:00:00.000000Z")
    )
    definition = FeatureDefinition(
        "features/customer",
        "Customer features",
        "project/demo",
        AssetRef(AssetId("table/customers"), AssetVersion("1")),
        (FeatureSpec("age", "numeric"),),
    )
    store.put_feature_definition(WorkspaceId("workspace-a"), definition)
    assert store.get_feature_definition(WorkspaceId("workspace-a"), definition.id) == definition
    assert store.get_feature_definition(WorkspaceId("workspace-b"), definition.id) is None


def test_feature_definition_service_enforces_monotonic_versions(tmp_path) -> None:
    store = SqliteMLLabStore(
        tmp_path / "ml.sqlite", migration_now=Instant("2026-09-22T00:00:00.000000Z")
    )
    service = FeatureDefinitionService(store)
    workspace = WorkspaceId("workspace-a")
    base = FeatureDefinition(
        "features/customer",
        "Customer features",
        "project/demo",
        AssetRef(AssetId("table/customers"), AssetVersion("1")),
        (FeatureSpec("age"),),
    )
    assert service.publish(workspace, base) == base
    assert service.publish(workspace, base) == base
    conflicting = FeatureDefinition(
        base.id,
        base.name,
        base.project_id,
        base.dataset,
        base.features,
        transform="different",
        version=1,
    )
    with pytest.raises(FeatureDefinitionConflict, match="already exists"):
        service.publish(workspace, conflicting)
    newer = FeatureDefinition(
        base.id,
        base.name,
        base.project_id,
        base.dataset,
        base.features,
        transform="standardize-v2",
        version=2,
    )
    assert service.publish(workspace, newer).version == 2
    assert service.get(workspace, base.id).version == 2
