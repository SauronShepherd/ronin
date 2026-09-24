from studio_storage.bundle_catalog_import_port import CatalogBundleImportStore
from studio_storage.postgres_core import PostgresMetadataStore


def test_postgres_metadata_store_implements_catalog_bundle_commit_port() -> None:
    store = object.__new__(PostgresMetadataStore)

    assert isinstance(store, CatalogBundleImportStore)
    assert "commit_catalog_import" in PostgresMetadataStore.__dict__
