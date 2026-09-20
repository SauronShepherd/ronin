from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_operations_runbook_documents_local_operating_contract() -> None:
    runbook = (ROOT / "docs" / "SYNTHETIC_DATA_STUDIO_OPERATIONS.md").read_text()
    for required in (
        "RONIN_DB",
        "RONIN_WORKSPACE_ID",
        "Modo offline",
        "Backup y restore",
        "quality_failed",
        "idempotency_key_conflict",
        "Frontera Ronin Pro",
    ):
        assert required in runbook


def test_frontend_exposes_backend_routes() -> None:
    source = (ROOT / "web" / "js" / "synthetic-data-studio.js").read_text()
    for route in (
        "/v1/synthetic-data-studio/generate",
        "/v1/synthetic-data-studio/catalog/assets",
        "/lineage",
        "/revisions",
    ):
        assert route in source
