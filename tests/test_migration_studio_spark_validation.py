import pytest

from studio_migration import SparkValidationPlan


def test_spark_plan_renders_native_schema_counts_and_multiset_checks() -> None:
    plan = SparkValidationPlan("orders", "full", ("schema", "counts", "multiset"))
    code = plan.render()
    assert "expected_aligned.exceptAll(actual_aligned)" in code
    assert "expected_df.count()" in code
    assert "expected_df.schema.fields" in code
    assert "collect(" not in code
    assert "expected_df.exceptAll(actual_df)" not in code


def test_keyed_plan_requires_keys_and_emits_key_health() -> None:
    with pytest.raises(ValueError, match="key_columns"):
        SparkValidationPlan("orders", "simple", ("keyed",))
    code = SparkValidationPlan("orders", "simple", ("keyed",), ("order_id",)).render()
    assert "groupBy(*key_columns)" in code
    assert "duplicate_keys" in code
    assert "keyed_cells" in code
    assert "eqNullSafe" in code
    assert "cell_diffs = cell_diffs.unionByName(diff_frame)" in code


def test_rendered_keyed_plan_is_python_syntax() -> None:
    code = SparkValidationPlan(
        "orders", "full", ("schema", "counts", "keyed"), ("order_id",), (("amount", 0.01),)
    ).render()
    compile(code, "generated-validation.py", "exec")
    assert "safe_join = expected_unique.join(actual_unique, '" not in code
