import ast

import pytest
from studio_migration import (
    MigrationUnit,
    ScopeSelection,
    SourceInventory,
    export_migration_script,
    extract_blueprint,
    generate_project,
    generate_pyspark,
    qualify_generated_project,
)


def test_blueprint_is_deterministic_and_auditable() -> None:
    blueprint = extract_blueprint(
        '{"conventions":{"io":"delta","layout":"src"},"topology":"package"}'
    )
    assert (
        blueprint.digest
        == extract_blueprint(
            '{"topology":"package","conventions":{"layout":"src","io":"delta"}}'
        ).digest
    )
    assert blueprint.rules[0].classification == "MANDATORY"


def test_pyspark_generation_is_deterministic_and_marks_qualification() -> None:
    blueprint = extract_blueprint('{"conventions":{"io":"delta"}}')
    first = generate_pyspark(name="orders", source_path="/input", blueprint=blueprint)
    second = generate_pyspark(name="orders", source_path="/input", blueprint=blueprint)
    assert first == second
    assert "qualification is required" in first.content
    assert first.blueprint_digest == blueprint.digest


def test_project_generation_and_static_qualification_are_provenance_bound() -> None:
    inventory = SourceInventory(
        "iics",
        "test",
        (),
        (MigrationUnit("iics:process:p1", "process", "orders-process", "ready"),),
    )
    selection = ScopeSelection(("iics:process:p1",))
    project = generate_project(
        inventory=inventory,
        selection=selection,
        blueprint=extract_blueprint('{"topology":"package"}'),
    )
    assert project.files[0].path == "src/orders_process.py"
    assert inventory.digest in project.files[0].content
    assert '"qualification_required":true' in project.manifest
    qualification = qualify_generated_project(project)
    assert qualification.status == "passed"
    assert qualification.project_digest == project.project_digest


def test_project_generation_rejects_unsupported_units() -> None:
    inventory = SourceInventory(
        "iics",
        "test",
        (),
        (MigrationUnit("iics:process:p1", "process", "unsupported-process", "unsupported"),),
    )
    with pytest.raises(ValueError, match="unsupported"):
        generate_project(inventory=inventory, selection=ScopeSelection(("iics:process:p1",)))


def test_exported_migration_script_is_portable_and_provenance_bound() -> None:
    inventory = SourceInventory(
        "iics", "test", (), (MigrationUnit("iics:process:p1", "process", "orders", "ready"),)
    )
    project = generate_project(inventory=inventory, selection=ScopeSelection(("iics:process:p1",)))
    exported = export_migration_script(project)
    assert exported.path == "ronin_migration.py"
    assert "--source" in exported.content
    assert "--output" in exported.content
    assert project.project_digest in exported.content
    assert "SparkSession" in exported.content
    ast.parse(exported.content, filename=exported.path)
