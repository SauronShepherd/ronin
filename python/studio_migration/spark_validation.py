"""Compile validation contracts into Spark-native validation plans/code."""
# Generated source lines are intentionally kept readable as Spark snippets.
# ruff: noqa: E501

from __future__ import annotations

from dataclasses import dataclass

from .validation import CheckMode, ReportLevel


@dataclass(frozen=True, slots=True)
class SparkValidationPlan:
    asset_id: str
    level: ReportLevel
    modes: tuple[CheckMode, ...]
    key_columns: tuple[str, ...] = ()
    tolerances: tuple[tuple[str, float], ...] = ()

    def __post_init__(self) -> None:
        if not self.asset_id or self.asset_id != self.asset_id.strip():
            raise ValueError("asset_id must be non-empty and trimmed")
        if self.level not in {"simple", "full"}:
            raise ValueError("level must be simple or full")
        if "keyed" in self.modes and not self.key_columns:
            raise ValueError("keyed Spark validation requires key_columns")
        object.__setattr__(self, "modes", tuple(dict.fromkeys(self.modes)))
        object.__setattr__(self, "key_columns", tuple(dict.fromkeys(self.key_columns)))
        object.__setattr__(self, "tolerances", tuple(sorted(self.tolerances)))

    def render(self, *, expected_var: str = "expected", actual_var: str = "actual") -> str:
        """Render an executable, dependency-free Spark DataFrame snippet.

        The snippet returns a list of dictionaries suitable for persisting as
        a Ronin evidence artifact. It deliberately uses Spark-native APIs and
        never calls ``collect`` on the compared datasets.
        """
        lines = [
            "from pyspark.sql import functions as F",
            "",
            f"expected_df = {expected_var}",
            f"actual_df = {actual_var}",
            "checks = []",
        ]
        if "schema" in self.modes:
            lines.extend(
                [
                    "expected_schema = [(f.name, f.dataType.simpleString(), f.nullable) for f in expected_df.schema.fields]",
                    "actual_schema = [(f.name, f.dataType.simpleString(), f.nullable) for f in actual_df.schema.fields]",
                    "checks.append({'check_id': 'schema', 'status': 'pass' if expected_schema == actual_schema else 'fail', 'expected': expected_schema, 'actual': actual_schema})",
                ]
            )
        if "counts" in self.modes:
            lines.extend(
                [
                    "expected_count = expected_df.count()",
                    "actual_count = actual_df.count()",
                    "checks.append({'check_id': 'row_count', 'status': 'pass' if expected_count == actual_count else 'fail', 'expected': expected_count, 'actual': actual_count, 'delta': actual_count - expected_count})",
                ]
            )
        if "multiset" in self.modes:
            lines.extend(
                [
                    "columns = sorted(set(expected_df.columns) | set(actual_df.columns))",
                    "expected_aligned = expected_df.select(*columns)",
                    "actual_aligned = actual_df.select(*columns)",
                    "expected_only = expected_aligned.exceptAll(actual_aligned)",
                    "actual_only = actual_aligned.exceptAll(expected_aligned)",
                    "expected_only_count = expected_only.count()",
                    "actual_only_count = actual_only.count()",
                    "checks.append({'check_id': 'multiset', 'status': 'pass' if expected_only_count == 0 and actual_only_count == 0 else 'fail', 'expected_only': expected_only_count, 'actual_only': actual_only_count})",
                ]
            )
        if "keyed" in self.modes:
            keys = ", ".join(repr(column) for column in self.key_columns)
            payload_columns = "payload_columns = sorted((set(expected_df.columns) | set(actual_df.columns)) - set(key_columns))"
            join_condition = " & ".join(
                f"(F.col('e.`{column.replace('`', '``')}`').eqNullSafe(F.col('a.`{column.replace('`', '``')}`')))"
                for column in self.key_columns
            )
            tolerance_map = repr(dict(self.tolerances))
            lines.extend(
                [
                    f"key_columns = {keys and '(' + keys + (',' if len(self.key_columns) == 1 else '') + ')'}",
                    "expected_keys = expected_df.groupBy(*key_columns).count().withColumnRenamed('count', '_expected_count')",
                    "actual_keys = actual_df.groupBy(*key_columns).count().withColumnRenamed('count', '_actual_count')",
                    "key_health = expected_keys.join(actual_keys, list(key_columns), 'full').fillna(0, ['_expected_count', '_actual_count'])",
                    "duplicate_keys = key_health.filter((F.col('_expected_count') > 1) | (F.col('_actual_count') > 1))",
                    "checks.append({'check_id': 'key_health', 'status': 'warn' if duplicate_keys.limit(1).count() else 'pass', 'duplicate_keys': duplicate_keys.count()})",
                    "unique_expected = expected_keys.filter(F.col('_expected_count') == 1).select(*key_columns)",
                    "unique_actual = actual_keys.filter(F.col('_actual_count') == 1).select(*key_columns)",
                    "safe_keys = unique_expected.join(unique_actual, list(key_columns), 'full')",
                    "expected_unique = expected_df.join(unique_expected, list(key_columns), 'inner').alias('e')",
                    "actual_unique = actual_df.join(unique_actual, list(key_columns), 'inner').alias('a')",
                    f"safe_join = expected_unique.join(actual_unique, {join_condition}, 'full')",
                    payload_columns,
                    f"tolerances = {tolerance_map}",
                    "diff_frames = []",
                    "for column in payload_columns:",
                    "    left = F.col(f'e.`{column}`')",
                    "    right = F.col(f'a.`{column}`')",
                    "    tolerance = F.lit(float(tolerances.get(column, 0.0)))",
                    "    equal = left.eqNullSafe(right) if column not in tolerances else (left.eqNullSafe(right) | (left.cast('double').isNotNull() & right.cast('double').isNotNull() & (F.abs(left.cast('double') - right.cast('double')) <= tolerance)))",
                    "    diff_frames.append(safe_join.filter(~equal).select(*[F.coalesce(F.col(f'e.`{key}`'), F.col(f'a.`{key}`')).alias(key) for key in key_columns], F.lit(column).alias('column'), F.lit('<>').alias('status'), left.cast('string').alias('expected'), right.cast('string').alias('actual')))",
                    "cell_diffs = diff_frames[0] if diff_frames else safe_join.limit(0).select(*key_columns, F.lit(None).cast('string').alias('column'), F.lit(None).cast('string').alias('status'), F.lit(None).cast('string').alias('expected'), F.lit(None).cast('string').alias('actual'))",
                    "for diff_frame in diff_frames[1:]:",
                    "    cell_diffs = cell_diffs.unionByName(diff_frame)",
                    "cell_diff_count = cell_diffs.count()",
                    "checks.append({'check_id': 'keyed_cells', 'status': 'pass' if cell_diff_count == 0 else 'fail', 'differences': cell_diff_count})",
                ]
            )
        lines.extend(
            [
                f"validation_result = {{'asset_id': {self.asset_id!r}, 'level': {self.level!r}, 'checks': checks}}",
                "validation_result",
            ]
        )
        return "\n".join(lines) + "\n"


__all__ = ("SparkValidationPlan",)
