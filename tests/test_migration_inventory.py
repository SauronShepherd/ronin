from __future__ import annotations

import pytest

from studio_migration import inventory_json_document


def test_inventory_classifies_every_object_and_reports_binding() -> None:
    report = inventory_json_document(
        '{"objects":[{"type":"job","id":"j-1","status":"manual_decision","notes":["Review schedule"],"bindings":[{"kind":"connection","source_ref":"prod-db"}]}]}',
        source_platform="databricks",
        source_version="2026.1",
        importer_version="ronin-databricks-0.1",
    )
    assert report.objects[0].source_key == ("job", "j-1")
    assert report.requires_manual_decision
    assert report.unresolved_bindings[0].source_ref == "prod-db"


def test_inventory_rejects_duplicates_and_malformed_documents() -> None:
    with pytest.raises(ValueError, match="exactly once"):
        inventory_json_document(
            '{"objects":[{"type":"job","id":"j"},{"type":"job","id":"j"}]}',
            source_platform="fabric",
            source_version="1",
            importer_version="test",
        )
    with pytest.raises(ValueError, match="objects array"):
        inventory_json_document(
            "{}", source_platform="fabric", source_version="1", importer_version="test"
        )
