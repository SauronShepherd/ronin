import pytest
from studio_storage.migration_registry import (
    STORAGE_MIGRATION_DOMAINS,
    MigrationDomain,
    MigrationRegistryError,
    migration_order,
)


def test_migration_order_is_deterministic_and_dependency_first() -> None:
    domains = (
        MigrationDomain("catalog", ("workspaces",)),
        MigrationDomain("audit", ("workspaces",)),
        MigrationDomain("workspaces"),
    )

    assert migration_order(domains) == ("workspaces", "audit", "catalog")


def test_registry_rejects_duplicates_and_missing_dependencies() -> None:
    with pytest.raises(MigrationRegistryError, match="duplicate"):
        migration_order((MigrationDomain("workspaces"), MigrationDomain("workspaces")))
    with pytest.raises(MigrationRegistryError, match="missing dependencies"):
        migration_order((MigrationDomain("catalog", ("workspaces",)),))


def test_registry_rejects_cycles() -> None:
    with pytest.raises(MigrationRegistryError, match="cycle"):
        migration_order((MigrationDomain("a", ("b",)), MigrationDomain("b", ("a",))))


def test_storage_registry_has_a_valid_public_order() -> None:
    order = migration_order(STORAGE_MIGRATION_DOMAINS)

    assert order[0] == "workspaces"
    assert set(order) == {domain.name for domain in STORAGE_MIGRATION_DOMAINS}
