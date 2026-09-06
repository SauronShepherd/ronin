"""Regenerate the demo notebook fixture from source-stable references."""

from __future__ import annotations

import json
from pathlib import Path

from studio_notebook import NotebookImportCell, import_notebook

NAMESPACE = "examples/demo/notebooks/etl.ronin.json"
OUTPUT = Path(__file__).parent / "notebooks" / "etl.ronin.json"

_CUSTOMERS = (
    "customers = {i: {'id': i, 'region': 'eu' if i % 2 else 'us'} for i in range(100)}\n"
)
_ORDERS = (
    "orders = [{'id': i, 'customer_id': i % 100, 'amount': i * 3} for i in range(500)]\n"
)
_TOTALS = (
    "totals = {}\n"
    "for order in orders:\n"
    "    region = customers[order['customer_id']]['region']\n"
    "    totals[region] = totals.get(region, 0) + order['amount']\n"
)

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
        "rows = [{'id': i, 'region': 'eu' if i % 2 else 'us'} for i in range(100)]\n"
        "print(f'extracted {len(rows)} customers')",
        (),
    ),
    (
        "extract-orders",
        "code",
        "python",
        "rows = [{'id': i, 'customer_id': i % 100, 'amount': i * 3} for i in range(500)]\n"
        "print(f'extracted {len(rows)} orders')",
        (),
    ),
    (
        "join-and-aggregate",
        "code",
        "python",
        _CUSTOMERS + _ORDERS + _TOTALS + "print(totals)",
        ("extract-customers", "extract-orders"),
    ),
    (
        "quality-check",
        "code",
        "python",
        _CUSTOMERS
        + _ORDERS
        + _TOTALS
        + "assert set(totals) == {'eu', 'us'}, totals\n"
        + "assert all(value > 0 for value in totals.values()), totals\n"
        + "print('quality checks passed')",
        ("join-and-aggregate",),
    ),
    (
        "publish",
        "code",
        "python",
        "import json\n"
        + _CUSTOMERS
        + _ORDERS
        + _TOTALS
        + "print(json.dumps({'dataset': 'revenue_by_region', 'rows': len(totals), 'totals': totals}, sort_keys=True))",
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
