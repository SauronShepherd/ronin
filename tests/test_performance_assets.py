from pathlib import Path

from ronin_plugin_performance.assets import inventory_asset


def test_inventory_asset_is_bounded_and_reports_sizes(tmp_path: Path):
    (tmp_path / "a.bin").write_bytes(b"a")
    (tmp_path / "b.bin").write_bytes(b"bb")
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "c.bin").write_bytes(b"ccc")
    result = inventory_asset(tmp_path, max_files=2)
    assert result["file_count"] == 2
    assert result["bytes"] == 3
    assert result["truncated"] is True
