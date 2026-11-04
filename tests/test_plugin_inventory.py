from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools import plugin_inventory
from tools.plugin_inventory import build_inventory, inspect_python_file


def test_inventory_contains_repository_plugin_surfaces() -> None:
    root = Path(__file__).resolve().parents[1]

    inventory = build_inventory(root)

    json.dumps(inventory)
    assert inventory["schema_version"] == 1
    assert inventory["summary"]["python_files"] > 0
    assert inventory["summary"]["routes"] > 0
    assert "ronin.plugins.v1" in inventory["entry_points"]
    assert "workspaces" in inventory["entry_points"]["ronin.plugins.v1"]
    assert inventory["entry_points"]["ronin.plugins.v1"]["logging"] == (
        "studio_plugin_observability.plugins:logging_factory"
    )
    assert inventory["entry_points"]["ronin.plugins.v1"]["monitoring"] == (
        "studio_plugin_observability.plugins:monitoring_factory"
    )
    assert inventory["entry_points"]["ronin.plugins.v1"]["data_engineering"] == (
        "studio_data_engineering.plugin:factory"
    )
    assert any(item["package"] == "studio_plugin_workspaces" for item in inventory["files"])


def test_inventory_generation_is_deterministic(tmp_path: Path) -> None:
    source_root = tmp_path / "python"
    tests_root = tmp_path / "tests"
    package = source_root / "studio_example"
    package.mkdir(parents=True)
    tests_root.mkdir()
    (package / "api.py").write_text(
        "from fastapi import APIRouter\n"
        "router = APIRouter()\n"
        "@router.get('/v1/example')\n"
        "def get_example():\n"
        "    return {}\n",
        encoding="utf-8",
    )
    (tests_root / "test_example.py").write_text("def test_example(): pass\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        '[project.entry-points."ronin.plugins.v1"]\nexample = "studio_example:factory"\n',
        encoding="utf-8",
    )

    first = build_inventory(tmp_path)
    second = build_inventory(tmp_path)

    assert first == second
    assert first["summary"] == {"python_files": 2, "test_files": 1, "routes": 1, "packages": 1}


def test_inventory_extracts_routes_without_importing_application_modules(tmp_path: Path) -> None:
    source_root = tmp_path / "python"
    tests_root = tmp_path / "tests"
    path = source_root / "studio_example" / "api.py"
    path.parent.mkdir(parents=True)
    tests_root.mkdir()
    path.write_text(
        "from fastapi import APIRouter\n"
        "router = APIRouter()\n"
        "@router.get('/v1/example')\n"
        "def get_example():\n"
        "    return {}\n"
        "# Job job schedule worker task\n",
        encoding="utf-8",
    )

    result = inspect_python_file(path, source_root, tests_root)

    assert result.package == "studio_example"
    assert result.routes == ({"method": "GET", "path": "/v1/example", "function": "get_example"},)
    assert "fastapi" in result.imports
    assert result.markers["jobs"] == 7


def test_inventory_does_not_assign_package_to_path_escaping_source_root(tmp_path: Path) -> None:
    source_root = tmp_path / "python"
    package = source_root / "studio_example"
    package.mkdir(parents=True)
    tests_root = tmp_path / "tests"
    tests_root.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_text("value = 1\n", encoding="utf-8")

    result = inspect_python_file(
        package / ".." / ".." / "outside.py",
        source_root,
        tests_root,
    )

    assert result.package is None


def test_inventory_skips_source_package_resolution_for_external_test_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_root = tmp_path / "python"
    source_root.mkdir()
    tests_root = tmp_path / "tests"
    tests_root.mkdir()
    test_file = tests_root / "test_surface.py"
    test_file.write_text("def test_surface():\n    pass\n", encoding="utf-8")

    def unexpected_package_lookup(*_args: object) -> str | None:
        pytest.fail("test files outside python/ do not need source package resolution")

    monkeypatch.setattr(plugin_inventory, "_package_for", unexpected_package_lookup)

    result = inspect_python_file(test_file, source_root, tests_root)

    assert result.test is True
    assert result.package is None
