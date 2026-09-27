import json
from pathlib import Path

import pytest

from tools.capability_status import CapabilityStatusError, validate_manifest


def manifest() -> dict[str, object]:
    return {
        "schema_version": 1,
        "capabilities": [{"id": "execution", "status": "implemented", "summary": "durable runs"}],
    }


def test_validates_public_manifest_shape() -> None:
    assert validate_manifest(manifest())["schema_version"] == 1


def test_rejects_duplicate_or_unknown_status() -> None:
    value = manifest()
    value["capabilities"] = [
        {"id": "execution", "status": "implemented", "summary": "ok"},
        {"id": "execution", "status": "future", "summary": "bad"},
    ]
    with pytest.raises(CapabilityStatusError, match="duplicate"):
        validate_manifest(value)


def test_repository_public_v1_ledger_is_valid() -> None:
    path = Path(__file__).parents[1] / "docs/product/public-v1-status.json"
    assert validate_manifest(json.loads(path.read_text(encoding="utf-8")))
