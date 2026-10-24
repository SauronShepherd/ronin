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


def test_public_matrix_covers_stable_family_ids_and_excludes_p9_from_release_scope() -> None:
    rows = _rows()
    assert len(rows) == 14
    assert [row[0].split()[0] for row in rows] == [f"P{i}" for i in range(1, 15)]
    assert all(len(row) == 7 for row in rows)
    assert all(row[1] in {"Implemented", "Partial", "Out of scope"} for row in rows)
    assert all(row[2] in {"Yes", "Partial", "No", "N/A"} for row in rows)
    assert all(row[3] in {"Yes", "No", "N/A"} for row in rows)
    assert all(cell.strip() for row in rows for cell in row)
    p9 = rows[8]
    assert p9[1:4] == ["Out of scope", "N/A", "N/A"]


def test_matrix_does_not_claim_release_qualification_while_ledger_is_incomplete() -> None:
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    assert ledger["release_status"] != "complete"
    assert ledger["progress"]["total"] == 13
    assert ledger["progress"]["percent"] == 0
    assert all(row[3] in {"No", "N/A"} for row in _rows())
    p9 = next(item for item in ledger["capabilities"] if item["id"] == "p9-genai-rag-agents")
    assert p9["status"] == "out_of_scope"


def test_matrix_observed_candidate_matches_status_ledger() -> None:
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    marker = "**Observed candidate:** `"
    line = next(line for line in MATRIX.read_text(encoding="utf-8").splitlines() if marker in line)
    candidate = line.split(marker, 1)[1].split("`", 1)[0]
    assert candidate == ledger["observed_main_sha"]
