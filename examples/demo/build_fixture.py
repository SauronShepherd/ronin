"""Regenerate the demo notebook fixture from source-stable references."""

from __future__ import annotations

import json
from pathlib import Path

from studio_notebook import NotebookImportCell, import_notebook

NAMESPACE = "examples/demo/notebooks/etl.ronin.json"
OUTPUT = Path(__file__).parent / "notebooks" / "etl.ronin.json"

CELLS: tuple[tuple[str, str, str | None, str, tuple[str, ...]], ...] = (
    (
        "intro",
        "markdown",
        None,
        "# Demo ETL\n\nSix-cell demo notebook used by the Ronin v0.1 acceptance journey.",
        (),
    ),
    (
        "extract-customers",
        "code",
        "python",
        "import json, pathlib\n"
        "rows = [{\"id\": i, \"region\": \"eu\" if i % 2 else \"us\"} for i in range(100)]\n"
        "pathlib.Path('/tmp/customers.json').write_text(json.dumps(rows))\n"
        "print(f'extracted {len(rows)} customers')",
        (),
    ),
    (
        "extract-orders",
        "code",
        "python",
        "import json, pathlib\n"
        "rows = [{\"id\": i, \"customer_id\": i % 100, \"amount\": i * 3} for i in range(500)]\n"
        "pathlib.Path('/tmp/orders.json').write_text(json.dumps(rows))\n"
        "print(f'extracted {len(rows)} orders')",
        (),
    ),
    (
        "join-and-aggregate",
        "code",
        "python",
        "import json, pathlib\n"
        "customers = {c['id']: c for c in json.loads(pathlib.Path('/tmp/customers.json').read_text())}\n"
        "orders = json.loads(pathlib.Path('/tmp/orders.json').read_text())\n"
        "totals = {}\n"
        "for o in orders:\n"
        "    region = customers[o['customer_id']]['region']\n"
        "    totals[region] = totals.get(region, 0) + o['amount']\n"
        "pathlib.Path('/tmp/totals.json').write_text(json.dumps(totals))\n"
        "print(totals)",
        ("extract-customers", "extract-orders"),
    ),
    (
        "quality-check",
        "code",
        "python",
        "import json, pathlib\n"
        "totals = json.loads(pathlib.Path('/tmp/totals.json').read_text())\n"
        "assert set(totals) == {'eu', 'us'}, totals\n"
        "assert all(v > 0 for v in totals.values()), totals\n"
        "print('quality checks passed')",
        ("join-and-aggregate",),
    ),
    (
        "publish",
        "code",
        "python",
        "import json, pathlib\n"
        "totals = json.loads(pathlib.Path('/tmp/totals.json').read_text())\n"
        "print(json.dumps({'dataset': 'revenue_by_region', 'rows': len(totals), 'totals': totals}))",
        ("quality-check",),
    ),
)


def build() -> str:
    cells = tuple(
        NotebookImportCell(
            reference=reference,
            kind=kind,
            source=source,
            dependency_references=dependencies,
            language=language,
        )
        for reference, kind, language, source, dependencies in CELLS
    )
    document = import_notebook(NAMESPACE, cells)
    return json.dumps(document.to_data(), indent=2, sort_keys=True) + "\n"


if __name__ == "__main__":
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(build(), encoding="utf-8")
