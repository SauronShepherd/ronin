from pathlib import Path

import pytest

from studio_quality import QualityRowsReferenceError, resolve_quality_rows
from studio_storage import LocalArtifactStore


def test_quality_rows_resolver_verifies_content_addressed_json(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path)
    ref = store.put_bytes(
        role="quality-rows",
        data=b'[{"id": 1}, {"id": 2}]',
        media_type="application/json",
    )
    assert resolve_quality_rows(ref.storage_ref, store) == ({"id": 1}, {"id": 2})


@pytest.mark.parametrize("reference", ["rows://opaque", "artifact://sha256/not-a-digest"])
def test_quality_rows_resolver_rejects_unverified_references(
    tmp_path: Path, reference: str
) -> None:
    with pytest.raises(QualityRowsReferenceError, match="artifact://sha256"):
        resolve_quality_rows(reference, LocalArtifactStore(tmp_path))
