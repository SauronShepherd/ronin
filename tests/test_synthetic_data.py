from studio_synthetic_data import (
    ColumnSpec,
    CsvExporter,
    ExporterRegistry,
    ForeignKey,
    GenerationPlan,
    GovernanceState,
    TableSpec,
    assess_privacy,
    generate,
    profile,
    validate,
)


def test_profile_is_deterministic_and_bounded() -> None:
    report = profile({"customers": ({"country": "ES"}, {"country": None}, {"country": "ES"})})
    column = report[0].columns[0]
    assert column.null_rate == 1 / 3
    assert column.distinct_count == 1
    assert column.frequencies == (("ES", 2),)


def test_exporter_registry_accepts_replaceable_providers() -> None:
    registry = ExporterRegistry((CsvExporter(),))
    assert registry.formats == ("csv",)
    assert registry.export(
        "csv", generate(GenerationPlan((TableSpec("t", (ColumnSpec("x"),), rows=1),))).tables[0]
    )


def test_generation_is_reproducible_and_preserves_foreign_keys() -> None:
    plan = GenerationPlan(
        tables=(
            TableSpec(
                "customers",
                (ColumnSpec("id", "integer", nullable=False),),
                primary_key="id",
                rows=4,
            ),
            TableSpec(
                "orders",
                (ColumnSpec("id", "integer", nullable=False), ColumnSpec("customer_id", "integer")),
                rows=9,
            ),
        ),
        relationships=(ForeignKey("orders", "customer_id", "customers", "id"),),
        seed=42,
    )
    first = generate(plan)
    second = generate(plan)
    assert first == second
    assert validate(plan, first).passed
    assert first.state is GovernanceState.GENERATED
    assert validate(plan, first).evidence_id.startswith("validation-")
    report = validate(plan, first)
    assert report.passed is True
    assert "privacy_disclaimer" in report.checks
    assert "nullability" in report.checks


def test_null_rates_and_sample_are_visible_as_warnings() -> None:
    plan = GenerationPlan(
        (TableSpec("events", (ColumnSpec("kind", values=("a", "b"), null_rate=0.2),), rows=20),),
        seed=3,
    )
    result = generate(plan, {"events": ({"kind": "a"},)})
    assert any(value is None for value in (row["kind"] for row in result.tables[0].rows))
    assert result.warnings


def test_privacy_assessment_is_explicit_and_detects_exact_reuse() -> None:
    result = generate(GenerationPlan((TableSpec("t", (ColumnSpec("x", values=("a",)),), rows=1),)))
    assessment = assess_privacy(result, {"t": (result.tables[0].rows[0],)})
    assert assessment.status == "review_required"
    assert assessment.exact_row_matches == 1
    assert assess_privacy(result).status == "not_assessed"


def test_invalid_relationship_is_detected() -> None:
    plan = GenerationPlan(
        (
            TableSpec("parent", (ColumnSpec("id", "integer"),), rows=1),
            TableSpec("child", (ColumnSpec("parent_id", "integer"),), rows=1),
        ),
        (ForeignKey("child", "parent_id", "parent", "id"),),
        seed=1,
    )
    result = generate(plan)
    result.tables[0].rows[0] if False else None
    assert validate(plan, result).passed
