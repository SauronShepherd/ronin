from __future__ import annotations

from types import SimpleNamespace

import pytest
from studio_core import WorkspaceId
from studio_ml.postgres import PostgresMLLabStore
from studio_storage.postgres_ml import PostgresMLStore


def _unconnected_store() -> PostgresMLStore:
    store = object.__new__(PostgresMLStore)
    store._dsn = "postgresql://ronin-test/ronin"
    return store


def _unconnected_feature_store(dsn: str) -> PostgresMLLabStore:
    store = object.__new__(PostgresMLLabStore)
    store._dsn = dsn
    return store


def test_postgres_bundle_feature_import_requires_same_database_and_writer() -> None:
    store = _unconnected_store()
    matching = _unconnected_feature_store("postgresql://ronin-test/ronin")
    store.validate_registry_bundle_import(feature_definitions=(object(),), feature_store=matching)

    other_database = _unconnected_feature_store("postgresql://ronin-test/other")
    with pytest.raises(ValueError, match="share one PostgreSQL database"):
        store.validate_registry_bundle_import(
            feature_definitions=(object(),), feature_store=other_database
        )

    without_writer = SimpleNamespace(_dsn="postgresql://ronin-test/ronin")
    with pytest.raises(ValueError, match="transaction-aware feature store"):
        store.validate_registry_bundle_import(
            feature_definitions=(object(),), feature_store=without_writer
        )


def test_postgres_bundle_import_rejects_cross_database_features_before_connecting() -> None:
    store = _unconnected_store()

    def unexpected_connection() -> object:
        pytest.fail("connection must not be opened for an invalid feature store")

    store._connect = unexpected_connection
    feature_store = _unconnected_feature_store("postgresql://ronin-test/other")

    with pytest.raises(ValueError, match="share one PostgreSQL database"):
        store.commit_registry_bundle_import(
            WorkspaceId("workspace"),
            experiments=(),
            runs=(),
            models=(),
            evaluations=(),
            feature_definitions=(object(),),
            feature_store=feature_store,
            now="2026-10-24T10:00:00.000000Z",
        )


def test_postgres_bundle_validation_does_not_require_a_feature_store_without_features() -> None:
    store = _unconnected_store()
    store.validate_registry_bundle_import(feature_definitions=(), feature_store=None)
