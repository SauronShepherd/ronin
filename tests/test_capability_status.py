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


def test_blocked_qualification_requires_traceable_blocking_conditions() -> None:
    value = manifest()
    value["qualification_status"] = "blocked"
    value["release_decision_checklist"] = "docs/product/RELEASE_DECISION_CHECKLIST_2026-11-03.md"
    value["blocking_conditions"] = [
        {
            "id": "candidate-identity",
            "status": "qualification_pending",
            "summary": "No clean candidate binds the evidence.",
            "evidence": (
                "docs/product/RELEASE_DECISION_CHECKLIST_2026-11-03.md#mandatory-release-gates"
            ),
        }
    ]
    assert validate_manifest(value)["blocking_conditions"] == value["blocking_conditions"]


def test_rejects_blocked_qualification_without_reason() -> None:
    value = manifest()
    value["qualification_status"] = "blocked"
    value["release_decision_checklist"] = "docs/product/RELEASE_DECISION_CHECKLIST_2026-11-03.md"
    with pytest.raises(CapabilityStatusError, match="requires blocking_conditions"):
        validate_manifest(value)


def test_rejects_incomplete_blocking_condition() -> None:
    value = manifest()
    value["qualification_status"] = "blocked"
    value["release_decision_checklist"] = "docs/product/RELEASE_DECISION_CHECKLIST_2026-11-03.md"
    value["blocking_conditions"] = [
        {"id": "license", "status": "human_decision", "summary": "Review pending."}
    ]
    with pytest.raises(CapabilityStatusError, match="evidence missing"):
        validate_manifest(value)


def test_repository_public_v1_ledger_is_valid() -> None:
    path = Path(__file__).parents[1] / "docs/product/public-v1-status.json"
    assert validate_manifest(json.loads(path.read_text(encoding="utf-8")))
