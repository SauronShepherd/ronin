from pathlib import Path


def test_public_plugin_testkit_package_is_clean_room_distributable() -> None:
    root = Path("packages/ronin-plugin-testkit")
    assert (root / "pyproject.toml").is_file()
    assert (root / "README.md").is_file()
    source = (root / "src/ronin_plugin_testkit/__init__.py").read_text(encoding="utf-8")
    assert "studio_plugin_testkit" in source
    assert "tests." not in source
