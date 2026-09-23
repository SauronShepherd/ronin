from __future__ import annotations

import io
import zipfile

import pytest
from studio_migration import MigrationUnit, SourceInventory, discover_iics_zip, select_scope


def _zip(files: dict[str, str]) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, value in files.items():
            archive.writestr(name, value)
    return stream.getvalue()


def test_iics_discovery_is_deterministic_and_resolves_mapping() -> None:
    raw = _zip(
        {
            "pkg/DTEMPLATE.json": '{"assetFrsGuid":"map-1","name":"orders"}',
            "pkg/MTT.json": '{"mappingId":"map-1","id":"proc-1"}',
        }
    )
    first = discover_iics_zip((("export.zip", raw),))
    second = discover_iics_zip((("export.zip", raw),))
    assert first.digest == second.digest
    assert {unit.state for unit in first.units} == {"ready"}
    assert {unit.kind for unit in first.units} == {"mapping", "process", "package"}


def test_iics_unresolved_mapping_is_review_required() -> None:
    raw = _zip({"pkg/MTT.json": '{"mappingId":"missing","id":"proc-1"}'})
    inventory = discover_iics_zip((("export.zip", raw),))
    process = next(unit for unit in inventory.units if unit.kind == "process")
    assert process.state == "review_required"
    assert "could not be resolved" in " ".join(process.notes)


def test_iics_rejects_unsafe_paths() -> None:
    unsafe = io.BytesIO()
    with zipfile.ZipFile(unsafe, "w") as archive:
        archive.writestr("../escape.json", "{}")
    with pytest.raises(ValueError, match="unsafe path"):
        discover_iics_zip((("export.zip", unsafe.getvalue()),))


def test_scope_closes_transitive_dependencies_with_reasons() -> None:
    inventory = SourceInventory(
        "test",
        "1",
        (),
        (
            MigrationUnit("a", "process", "a", "ready", ("b",)),
            MigrationUnit("b", "mapping", "b", "ready", ("c",)),
            MigrationUnit("c", "package", "c", "ready"),
        ),
    )
    selection = select_scope(inventory, ("a",))
    assert selection.selected == ("a",)
    assert selection.auto_included == ("b", "c")
    assert ("b", "required by a") in selection.reasons
    assert ("c", "required by b") in selection.reasons
