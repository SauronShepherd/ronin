# Ronin Studio

Ronin Studio is being built from the product, architecture, construction and test specifications defined for the unified Studio project. The target is a local-first, Git-native environment where reactive notebooks and visual Spark pipelines are two views of a shared intermediate representation.

## Current status

The repository is at **E0 — Foundation**. This commit establishes the Python package layout, static-quality configuration, an executable architecture boundary check and CI. Product capabilities described by the specification are **not yet claimed as implemented**.

## Development

```bash
python -m pip install -e '.[dev]'
make check
```

`make check` runs formatting/linting, strict type checking, the architecture gate and tests. The architecture gate rejects forbidden I/O in pure domain packages before product code is allowed to grow around the wrong dependency direction.

## Layout

- `python/` — product Python packages.
- `tests/` — executable quality and architecture contracts.
- `tools/` — repository quality gates.
- `docs/automation/` — durable progress, backlog and decision log for incremental autonomous work.

The project deliberately starts with a narrow foundation. New packages and capabilities are added only with their tests and evidence.
