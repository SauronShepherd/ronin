from studio_migration import analyze_pyspark


def test_static_analysis_finds_driver_partition_udf_and_cache_risks() -> None:
    findings = analyze_pyspark(
        """import pyspark.sql.functions as F
df.cache()
df.collect()
df.repartition(1)
df.withColumn('x', F.udf(lambda x: x)('value'))
"""
    )
    rules = {item.rule_id for item in findings}
    assert {
        "DRIVER_MATERIALIZATION",
        "SINGLE_PARTITION",
        "PYTHON_UDF",
        "CACHE_WITHOUT_UNPERSIST",
    } <= rules


def test_static_analysis_reports_invalid_generated_python() -> None:
    findings = analyze_pyspark("def broken(:")
    assert findings[0].rule_id == "PYTHON_SYNTAX"
    assert findings[0].severity == "error"
