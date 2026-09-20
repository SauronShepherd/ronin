from __future__ import annotations

import json
from pathlib import Path

from tools.plugin_inventory import build_inventory, inspect_python_file


def test_inventory_is_deterministic_and_contains_plugin_surfaces() -> None:
    root = Path(__file__).resolve().parents[1]

    first = build_inventory(root)
    second = build_inventory(root)

    assert first == second
    assert first["schema_version"] == 1
    assert first["summary"]["python_files"] > 0
    assert first["summary"]["routes"] > 0
    assert "ronin.plugins.v1" in first["entry_points"]
    assert "workspaces" in first["entry_points"]["ronin.plugins.v1"]
    assert first["entry_points"]["ronin.plugins.v1"]["logging"] == (
        "studio_plugin_observability.plugins:logging_factory"
    )
    assert first["entry_points"]["ronin.plugins.v1"]["monitoring"] == (
        "studio_plugin_observability.plugins:monitoring_factory"
    )
    assert any(item["package"] == "studio_plugin_workspaces" for item in first["files"])


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
        "    return {}\n",
        encoding="utf-8",
    )

    result = inspect_python_file(path, source_root, tests_root)

    assert result.package == "studio_example"
    assert result.routes == ({"method": "GET", "path": "/v1/example", "function": "get_example"},)
    assert "fastapi" in result.imports


def test_inventory_json_is_serializable() -> None:
    root = Path(__file__).resolve().parents[1]
    json.dumps(build_inventory(root))
