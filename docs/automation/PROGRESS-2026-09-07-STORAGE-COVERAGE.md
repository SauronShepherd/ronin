# Ronin progress — 2026-09-07 storage per-file coverage ratchet

## Scope

This is the next bounded increment of the storage implementation collapse after the cursor-contract extraction.

It adds an additive per-file coverage discipline for `python/studio_storage` while preserving the existing T2 package gate at **>=90%**. It does not alter product behavior, storage semantics, durability, acceptance skips or security policy.

## Evidence-led thresholds

Exact-main CI #610 on `b40626ba9cf773441ec523cedfbb10e2b2c7493b` reported these rounded storage line/branch combined coverage figures:

- `artifacts.py`: 90%
- `async_artifacts.py`: 95%
- `async_store.py`: 95%
- `fenced_sqlite.py`: 95%
- `memory.py`: 89%
- `paged_store.py`: 94%
- `pagination.py`: 98%
- `sqlite.py`: 59% rounded in the tabular report

PR qualification then exposed the underlying coverage JSON value for `sqlite.py` as **58.92%**. The ratchet uses that exact measured value rather than the rounded display value.

A blanket 80% file floor would therefore fail the existing canonical SQLite implementation immediately rather than ratchet it safely.

The new gate instead applies:

- default per-file floor: **80%** for every current or newly added `studio_storage` Python file;
- explicit legacy baseline: **58.92%** for `sqlite.py` only;
- missing coverage evidence fails closed;
- stale baseline entries fail closed;
- malformed or out-of-range evidence fails closed;
- the legacy baseline cannot be configured above the default threshold and cannot regress below its recorded floor.

This makes `sqlite.py=58.92` a visible transitional debt item rather than weakening the existing aggregate T2 >=90% policy.

## Why this slice precedes broader SQLite relocation

Current `SqliteJobStore` is still composed through `paged_store -> fenced_sqlite -> sqlite`, and `paged_store.SqliteJobStore` still owns final keyset/dense-event read SQL. Moving all of that SQL plus lease-fenced write internals through a connector-only rewrite would be a much broader semantic change.

The coverage ratchet is an independent part of the documented storage-collapse plan and is safe to land first. It creates a non-regression boundary before the canonical SQLite file is refactored and tested upward.

## Remaining storage-collapse work

1. raise canonical `sqlite.py` coverage from its explicit 58.92% legacy baseline toward the normal >=80% file floor with strong behavior tests;
2. move final newest-first keyset and dense Run-event SQL into canonical `sqlite.py`;
3. remove `paged_store.SqliteJobStore` once canonical SQLite exposes those reads directly;
4. compose active-lease fencing around shared internal mutation helpers instead of duplicating SQL statements;
5. remove duplicate same-named SQLite classes where practical without changing the public import contract;
6. retire the `sqlite.py=58.92` exception as soon as the canonical adapter meets the normal floor.

Do not start D1 CLI in parallel with this remaining storage collapse.
