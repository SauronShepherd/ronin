from pathlib import Path

import pytest

from tools.openapi_snapshot import check


def test_public_openapi_snapshot_is_current() -> None:
    root = Path(__file__).parents[1]
    assert len(check(root / "api/openapi-v1.json", root / "api/openapi-v1.sha256")) == 64


def test_openapi_snapshot_rejects_drift(tmp_path: Path) -> None:
    document = tmp_path / "openapi.json"
    snapshot = tmp_path / "openapi.sha256"
    document.write_text('{"openapi":"3.1.0"}', encoding="utf-8")
    snapshot.write_text("0" * 64, encoding="utf-8")
    with pytest.raises(ValueError, match="mismatch"):
        check(document, snapshot)
