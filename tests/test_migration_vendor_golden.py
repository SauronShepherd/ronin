from __future__ import annotations

import json
from pathlib import Path

import pytest

from studio_migration import (
    discover_databricks,
    discover_dataiku,
    discover_fabric,
    discover_foundry,
)
from studio_migration.databricks import translate_notebook_job
from studio_migration.dataiku import translate_code_recipes
from studio_migration.fabric import translate_notebook_items
from studio_migration.foundry import translate_python_functions

ROOT = Path(__file__).parent / "fixtures" / "migration"


@pytest.mark.parametrize(
    ("filename", "discover", "translate", "platform", "nodes", "translated", "unsupported"),
    [
        ("databricks-job.json", discover_databricks, translate_notebook_job, "databricks", 2, 3, 0),
        (
            "fabric-items.json",
            discover_fabric,
            translate_notebook_items,
            "microsoft-fabric",
            1,
            1,
            1,
        ),
        (
            "foundry-functions.json",
            discover_foundry,
            translate_python_functions,
            "palantir-foundry-aip",
            1,
            1,
            1,
        ),
        ("dataiku-recipes.json", discover_dataiku, translate_code_recipes, "dataiku-dss", 2, 2, 1),
    ],
)
def test_vendor_golden_inventory_and_translation_are_deterministic(
    filename, discover, translate, platform, nodes, translated, unsupported
) -> None:
    document = (ROOT / filename).read_bytes()
    first = discover(document, source_version="golden-2026")
    second = discover(document, source_version="golden-2026")
    conversion = translate(document, source_version="golden-2026")

    assert first == second
    assert first.source_platform == platform
    assert first.digest == second.digest
    assert len(conversion.workflow.pipeline.nodes) == nodes
    statuses = [item.status for item in conversion.report.objects]
    assert statuses.count("translated") == translated
    assert statuses.count("unsupported") == unsupported
    assert json.loads(conversion.workflow.to_json())["id"]
    assert len(conversion.report.digest) == 64
