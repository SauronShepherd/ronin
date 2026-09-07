# Ronin progress — 2026-09-07 storage collapse, cursor contract increment

## Scope

This is the first bounded increment of the storage implementation collapse identified after S1. It moves opaque C0 pagination cursor encoding, decoding and validation out of `paged_store.py` into a dedicated storage-neutral `studio_storage.pagination` module.

The exported JobStore behavior is intentionally unchanged. Newest-first job keyset pagination, Run-bound event cursors, dense Run-global projection, filter binding, bounded cursor size and fail-closed coordinate validation keep the same v1 wire semantics.

## Why this cut is deliberately narrow

Current `SqliteJobStore` is still composed through `paged_store -> fenced_sqlite -> sqlite`. Moving all final SQL and lease-fenced mutations in one connector edit would require a broad rewrite of the large canonical SQLite adapter and would increase risk without local checkout execution in this environment.

This increment therefore removes cursor semantics from the wrapper before moving SQL. Existing private test-facing helper names remain compatibility aliases to the canonical functions; there is only one implementation of those rules.

## Qualification

Targeted tests directly qualify the canonical cursor module and assert that the legacy private aliases delegate to it rather than retaining duplicate implementations. Existing storage pagination conformance remains authoritative for in-memory/SQLite behavior.

No coverage, security, durability, qualification or skip gate is weakened.

## Remaining storage-collapse work

The next storage-collapse increment remains:

1. move final newest-first keyset and dense Run-event SQL into the canonical SQLite implementation;
2. remove the `paged_store.SqliteJobStore` subclass once canonical SQLite exposes those reads directly;
3. compose active-lease fencing around shared internal mutation helpers instead of duplicating SQL statements;
4. remove duplicate same-named SQLite classes where practical without changing the public import;
5. add a defensible per-file coverage floor for safety-critical storage while preserving the existing T2 >=90% package gate.

Do not start D1 CLI in parallel with this remaining storage collapse.
