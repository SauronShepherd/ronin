from __future__ import annotations

import pytest

from tools.migration_certification import STATUSES, CertificationError, validate


def _evidence() -> dict[str, object]:
    digest = "a" * 64
    return {
        "schema": "ronin.migration-certification/v1",
        "profile": "fabric",
        "source_inventory_digest": digest,
        "report_digest": "b" * 64,
        "bundle_roundtrip_digest": "c" * 64,
        "execution_status": "passed",
        "classification_counts": dict.fromkeys(STATUSES, 0) | {"translated": 1},
        "source_object_ids": ["source-1"],
        "classifications": [{"source_object_id": "source-1", "status": "translated"}],
    }


def test_certification_requires_complete_profile_evidence() -> None:
    assert validate(_evidence())["profile"] == "fabric"


@pytest.mark.parametrize(
    "field", ["source_inventory_digest", "report_digest", "bundle_roundtrip_digest"]
)
def test_certification_rejects_invalid_digests(field: str) -> None:
    evidence = _evidence()
    evidence[field] = "bad"
    with pytest.raises(CertificationError, match="digest"):
        validate(evidence)


def test_certification_rejects_incomplete_or_unexecuted_evidence() -> None:
    evidence = _evidence()
    evidence["execution_status"] = "review_required"
    with pytest.raises(CertificationError, match="execution_status"):
        validate(evidence)
    evidence = _evidence()
    evidence["classification_counts"] = dict.fromkeys(STATUSES, 0)
    with pytest.raises(CertificationError, match="at least one"):
        validate(evidence)


def test_certification_rejects_duplicate_or_mismatched_source_inventory() -> None:
    evidence = _evidence()
    evidence["source_object_ids"] = ["source-1", "source-1"]
    with pytest.raises(CertificationError, match="unique"):
        validate(evidence)
    evidence = _evidence()
    evidence["source_object_ids"] = ["source-1", "source-2"]
    with pytest.raises(CertificationError, match="count"):
        validate(evidence)


def test_certification_requires_exhaustive_per_object_classifications() -> None:
    evidence = _evidence()
    evidence.pop("classifications")
    with pytest.raises(CertificationError, match="classifications"):
        validate(evidence)
    evidence = _evidence()
    evidence["classifications"] = [{"source_object_id": "other", "status": "translated"}]
    with pytest.raises(CertificationError, match="cover"):
        validate(evidence)
    evidence = _evidence()
    evidence["classification_counts"] = dict.fromkeys(STATUSES, 0) | {"partial": 1}
    with pytest.raises(CertificationError, match="match"):
        validate(evidence)
