from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_backfill_cancellation_uses_visible_id_and_accessible_confirmation() -> None:
    source = (ROOT / "web/js/backfill-accessibility.js").read_text(encoding="utf-8")

    assert 'id="backfill-cancel-id"' in source
    assert "confirmImpact(`Cancel backfill ${id}?" in source
    legacy = (ROOT / "web/js/features.js").read_text(encoding="utf-8")
    assert "window.prompt('Backfill ID to cancel')" not in legacy
