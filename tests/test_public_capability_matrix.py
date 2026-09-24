from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).parents[1]
MATRIX = ROOT / "docs/product/PUBLIC_V1_CAPABILITY_MATRIX.md"
LEDGER = ROOT / "docs/product/public-v1-status.json"


def _rows() -> list[list[str]]:
    rows: list[list[str]] = []
    in_table = False
    for line in MATRIX.read_text(encoding="utf-8").splitlines():
        if line.startswith("| Capability | Implemented |"):
            in_table = True
            continue
        if in_table and line.startswith("| ---"):
            continue
        if in_table and line.startswith("| "):
            rows.append([cell.strip() for cell in line.strip("|").split("|")])
            continue
        if in_table and line and not line.startswith("|"):
            break
    return rows


def test_public_matrix_covers_exactly_p1_to_p14_and_required_fields() -> None:
    rows = _rows()
    assert len(rows) == 14
    assert [row[0].split()[0] for row in rows] == [f"P{i}" for i in range(1, 15)]
    assert all(len(row) == 7 for row in rows)
    assert all(row[1] in {"Implemented", "Partial"} for row in rows)
    assert all(row[2] in {"Yes", "Partial", "No"} for row in rows)
    assert all(row[3] in {"Yes", "No"} for row in rows)
    assert all(cell.strip() for row in rows for cell in row)


def test_matrix_does_not_claim_release_qualification_while_ledger_is_incomplete() -> None:
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    assert ledger["release_status"] != "complete"
    assert all(row[3] == "No" for row in _rows())
