from pathlib import Path

import pytest

from tools.generate_release_case_inventory import (
    classify_case,
    parse_cases,
    parse_routes,
    render_inventory,
)


def test_parse_cases_preserves_source_metadata_and_section() -> None:
    lines = [
        "## Runtime and packaging",
        "#### CORE-001 — Doctor command",
        "- **Área / prioridad / tipo / nivel:** CLI; `P0`; `A`; contract. "
        "**Estado:** `not-run`; **Responsable lógico:** `runtime`. "
        "**PASS:** doctor reports ready. **FAIL:** missing dependency.",
        "## Browser",
        "#### RG-WEB-001 — Installed UI",
        "- **Categoría/feature:** Studio Web. **Tipo:** M. **Prioridad:** P1. "
        "**Owner lógico:** `studio`. **Estado en esta tarea:** `not-run`.",
    ]

    cases = parse_cases(lines)

    assert [(case.case_id, case.section) for case in cases] == [
        ("CORE-001", "Runtime and packaging"),
        ("RG-WEB-001", "Browser"),
    ]
    assert (cases[0].area, cases[0].priority, cases[0].kind) == ("CLI", "P0", "A")
    assert (cases[0].owner, cases[0].status) == ("runtime", "not-run")
    assert cases[0].acceptance == "doctor reports ready."
    assert (cases[1].area, cases[1].priority, cases[1].kind) == (
        "Studio Web",
        "P1",
        "M",
    )
    assert (cases[1].owner, cases[1].status) == ("studio", "not-run")


def test_parse_cases_rejects_duplicate_identifiers() -> None:
    lines = [
        "#### CORE-001 — First",
        "#### CORE-001 — Duplicate",
    ]

    with pytest.raises(ValueError, match="Duplicate case IDs: CORE-001"):
        parse_cases(lines)


def test_priority_is_not_inferred_from_procedure_text() -> None:
    lines = [
        "#### CORE-002 — Untagged card",
        "- **Objetivo y riesgo:** exercise a P0 boundary only as a negative fixture.",
    ]

    assert parse_cases(lines)[0].priority == "N/D"
    assert parse_cases(lines)[0].acceptance == "N/D"


def test_acceptance_is_extracted_from_an_explicit_pass_fail_label() -> None:
    cases = parse_cases(
        [
            "#### CORE-003 — Explicit acceptance",
            "- **PASS/FAIL:** PASS if the state is stable; FAIL if it diverges.",
            "#### CORE-004 — No acceptance label",
            "- **Objective:** P0 boundary remains absent.",
        ]
    )

    assert cases[0].acceptance == "PASS if the state is stable; FAIL if it diverges."
    assert cases[1].acceptance == "N/D"


def test_acceptance_supports_explicit_source_label_variants() -> None:
    cases = parse_cases(
        [
            "#### CORE-005 — Labeled acceptance",
            "- **PASS (acceptance criterion):** the result is deterministic. "
            "**FAIL:** state diverges.",
            "#### CORE-006 — Expected result label",
            "- **Resultado esperado / PASS:** no partial state remains. **Evidencia:** receipt.",
        ]
    )

    assert cases[0].acceptance == "the result is deterministic."
    assert cases[1].acceptance == "no partial state remains."


def test_later_source_metadata_variants_are_read_without_inference() -> None:
    case = parse_cases(
        [
            "#### RG-UI-001 — Explicit later format",
            "- **ID/feature/risk/priority:** UI; P1/M/ready; owner: web+release; status: proposed.",
            "- **PASS:** UI stays operable.",
        ]
    )[0]

    assert case.priority == "P1"
    assert case.kind == "M"
    assert case.owner == "web+release"
    assert case.status == "proposed"


def test_scope_mapping_applies_product_boundaries_and_local_no_ci_policy() -> None:
    assert classify_case("AI-001")[1] == ("Out of scope as a capability; verify absence only")
    assert classify_case("AI-004")[0].startswith("P10")
    assert classify_case("IAM-003")[0].startswith("Ronin Pro")
    assert classify_case("RG-SEC-016")[1].startswith("Out of Public v1")
    assert classify_case("REL-001")[1].startswith("Replace CI-specific")
    assert classify_case("RG-CI-RUN-001")[0].startswith("P14 local")
    assert classify_case("RG-STR-PORT-001")[0].startswith("P11/P14")
    assert classify_case("RG-STR-001")[0] == "P11 streaming"


def test_parse_routes_marks_retired_routes_and_rejects_duplicates() -> None:
    lines = [
        "| WEB-ROUTE-001 | `home` | UI and API | not-run |",
        "| WEB-ROUTE-002 | `genai` (retirada) | legacy only | out_of_scope |",
    ]

    routes = parse_routes(lines)

    assert [(route[0], route[2]) for route in routes] == [
        ("WEB-ROUTE-001", "activa"),
        ("WEB-ROUTE-002", "retirada"),
    ]
    with pytest.raises(ValueError, match="Duplicate WEB-ROUTE IDs"):
        parse_routes(lines + [lines[0]])


def test_render_inventory_writes_counts_hash_and_traceable_rows(tmp_path: Path) -> None:
    source = tmp_path / "master.md"
    output = tmp_path / "inventory.md"
    source.write_text(
        "## Release\n"
        "#### REL-001 — Build wheel\n"
        "- **Prioridad:** P0. **Tipo:** A.\n"
        "| WEB-ROUTE-001 | `home` | UI + API | not-run |\n",
        encoding="utf-8",
    )

    text, case_count, route_count, active_count = render_inventory(source, output)

    assert (case_count, route_count, active_count) == (1, 1, 1)
    assert output.read_text(encoding="utf-8") == text
    assert "Fuente canónica: `master.md`" in text
    assert "System.Object[]" not in text
    assert "## Catálogo íntegro de 1 fichas" in text
    assert "| REL-001 | Release | Build wheel |" in text
    assert "| WEB-ROUTE-001 | home | activa |" in text
