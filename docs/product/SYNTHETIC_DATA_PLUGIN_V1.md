# Govern Studio Plugin v1

Govern Studio is Ronin's community plugin for reproducible local fixtures. It
starts from an explicit schema and can optionally consume a small sample to
infer categorical values. The sample is never copied wholesale and the result
is not presented as anonymised or privacy-preserving.

## Workflow

`plan -> generate -> validate -> export`

The plan owns tables, columns, row counts, primary keys, foreign keys and a
seed. Generation is deterministic for the same plan and seed. Validation is a
separate gate that checks table shape, primary-key uniqueness and referential
integrity. An optional sample can be profiled before generation; the profile
records row counts, null rates, distinct values and a bounded top-frequency
list. Exporters are replaceable providers through `ExporterRegistry`; the
built-ins are CSV, JSON, JSONL and XML. Delta, Iceberg and Hudi are optional
table-provider manifests and remain non-writable until their dependencies are
installed.

## Plugin boundary

The plugin id is `com.ronin.synthetic-data-studio`. It provides
`synthetic-data-studio.plan.v1`, `synthetic-data-studio.generate.v1`,
`synthetic-data-studio.validate.v1` and `synthetic-data-studio.export.v1`, plus
REST contribution points under `/v1/synthetic-data-studio/`. The implementation package keeps its technical
`studio_synthetic_data` name for compatibility with the current Python API.
It depends only on the public plugin contract and the
Python standard library, so a future Parquet, SQLite or Delta exporter can be
added without changing the generator.

## Safety and limits

The local engine intentionally favors explainability over statistical ambition.
It currently models primitive types, null rates, categorical values, numeric
ranges, deterministic identifiers and declared relationships. It does not infer
business rules, guarantee privacy, or replace review for sensitive data. Future
extensions should add versioned profilers, business-rule providers, validation
metrics and isolated workers for large datasets rather than putting opaque
model calls in the core generator.
