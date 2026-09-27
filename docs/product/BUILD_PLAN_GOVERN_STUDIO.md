# Govern Studio Build Plan

## 0. Delivery contract

Implement Govern Studio as a Ronin community plugin. Every phase must leave the
host buildable, the feature disableable and the data recoverable.

Definition of done:

- public contracts and schemas are versioned;
- clean install discovers the plugin by entry point;
- deterministic generation works from schema and optional sample;
- relationships and constraints are enforced or explicitly reported;
- validation produces dimension-level evidence;
- artifacts are immutable, checksummed and run-scoped;
- publication requires policy and configured approval;
- exporters are independent providers;
- REST, CLI, SDK and UI call the same application services;
- failure, cancellation, retry and cleanup are tested;
- non-DP output never receives a formal privacy claim.

## 1. Target layout

```text
python/studio_synthetic_data/
  contracts.py plan.py profile.py graph.py generators.py constraints.py
  validation.py privacy.py artifacts.py exporters.py application.py plugin.py
  migrations/ schemas/
tests/test_govern_studio_*.py
web/js/features/govern-studio.js
web/styles/govern-studio.css
docs/product/GOVERN_STUDIO_PROPOSAL.md
docs/product/GOVERN_STUDIO_OPERATIONS.md
docs/plugin-authoring/govern-studio-provider.md
```

Keep `studio_synthetic_data` as a compatibility package name during migration;
all user-facing ids use `com.sauronshepherd.ronin.govern-studio` and
`govern-studio/v1`.

## 2. Phase 0 — baseline and flags

### Implementation

1. Add an ADR declaring Govern Studio a vertical plugin.
2. Freeze plugin id, API version and capability names.
3. Add temporary flags:

```text
RONIN_GOVERN_STUDIO_DISCOVERY=on|off
RONIN_GOVERN_STUDIO_API=off|shadow|on
RONIN_GOVERN_STUDIO_EXPORT=off|local|all
RONIN_GOVERN_STUDIO_MAX_ROWS=<int>
RONIN_GOVERN_STUDIO_MAX_BYTES=<int>
```

4. Give every flag an owner, metric and removal release.

### Tests and exit

Test deterministic discovery, duplicate ids/routes, API mismatch, degraded
optional startup, disabled contributions and clean shutdown. Exit when the
existing Ronin journey is unchanged with the plugin disabled.

## 3. Phase 1 — contracts and canonical plan

### Files

`contracts.py`, `plan.py`, `schemas/govern-studio.plan.v1.json`,
`test_govern_studio_contracts.py`.

### Implementation

Define frozen DTOs for workspace/request/plan/run/profile/report/artifact ids,
tables, columns, keys, relations, constraints, expectations, generation options,
privacy posture and export destinations. Validate JSON Schema 2020-12 before
domain validation. Canonicalize sorted keys, normalized numbers and explicit
nulls; hash canonical UTF-8 with SHA-256. Implement `to_payload()` and
`from_payload()` round trips.

Domain validation must check graph references, composite-key arity, logical type
compatibility, provider capabilities, row/byte limits, destination schemes,
intended use, secret absence and extension namespace rules.

### Acceptance

- key ordering does not change the fingerprint;
- seed/provider/engine changes do;
- bad references return JSON-path diagnostics;
- plans contain no sample rows, secrets or credentials;
- invalid destination and missing intended use fail before execution.

## 4. Phase 2 — sample readers and profiling

### Implementation

Create a `SampleReader` port and CSV, JSONL and SQLite adapters. Readers stream
rows, enforce byte/row/time limits and never log values. Produce versioned profile
evidence containing row counts, logical types, null rates, bounded distinct
counts, numeric summaries, quantiles, histograms, top-k categories, date range,
candidate keys/FKs, duplicate rate and sensitivity warnings.

Store only summaries by default. Record sampling method, rows read, source
fingerprint, algorithm version, redaction policy, creation and expiry.

FK suggestions combine name similarity, type compatibility, overlap, parent
uniqueness and cardinality. A suggestion cannot activate a relation without
user confirmation or trusted catalog metadata.

### Tests

Malformed input, invalid encoding, huge fields, empty tables, mixed types,
expired profiles, raw-value leakage, deterministic reports and low-confidence
relationship suggestions.

## 5. Phase 3 — relationship graph and execution plan

Build table nodes and FK edges; validate parent keys and compatible types;
topologically sort acyclic components; detect cycles; compile two-phase cycles;
make bridge-table requirements explicit; compile cardinality distributions; and
estimate rows, bytes, memory and duration before work starts.

Reject requests exceeding workspace or request budgets. Tests cover missing
parents, duplicate keys, type mismatch, cycles, zero-row parents, bridge tables
and stable ordering across processes.

## 6. Phase 4 — generator provider SDK

```python
class ColumnGenerator(Protocol):
    manifest: GeneratorManifest
    def fit(self, profile, config) -> FitReceipt: ...
    def generate(self, request) -> Iterator[object]: ...
```

Provider manifests declare id/version, logical types, claims, resource profile,
license and seed semantics. Discover via `ronin.generators.v1`; never install
packages at runtime. Record a provider lock in every run.

Baseline providers: sequential integer/UUID keys, weighted categories, bounded
integer/float, date/timestamp, boolean, email placeholder, regex-safe identifier,
null injection, derived values and parent-key sampling. Optional statistical or
DP providers run in workers and cannot broaden claims implicitly.

Derive independent sub-seeds from plan fingerprint, table, column, provider and
batch. This permits parallelism without losing reproducibility for the same
engine/provider lock.

Tests cover reproducibility, parallel batches, undeclared types, timeout,
provider exception, missing provider on resume and filesystem isolation.

## 7. Phase 5 — constraints

Implement a typed AST and compiler for range, inequality, conditional null,
conditional value, regex, date order, FK, cardinality, aggregate,
mutual-exclusion and functional-dependency rules.

Each constraint has id, version, severity, scope, enforcement mode and
`on_violation`: `fail`, `reject_row`, `repair` or `warn`. Order constraints by
dependency; cap reject attempts; report input/changed/rejected/invalid counts.
Repair must preserve original candidate evidence and is forbidden for sensitive
outputs unless a policy allows it.

Tests cover null semantics, impossible constraints, overlap, deterministic order,
repair accounting and warning-to-gate behavior.

## 8. Phase 6 — expectations and validation

Create an expectation registry and report protocol. Implement schema, volume,
completeness, uniqueness, integrity, distribution, relationship, business-rule,
privacy-indicator and export-verification expectations.

Each result stores id, dimension, target, threshold, observed value, status,
severity, duration, evidence reference and safe diagnostics. Skipped is not
passed. Reports aggregate by table, column, dimension and severity and receive a
stable fingerprint.

```json
{
  "report_id":"validation_01",
  "plan_fingerprint":"sha256:...",
  "disposition":"fit_for_intended_use|not_fit|needs_review",
  "expectations":[],
  "warnings":[],
  "claims":[],
  "evidence_id":"validation-..."
}
```

Test exact threshold boundaries, zero-row behavior, redaction, report hashing,
cross-table checks and incomplete validation.

## 9. Phase 7 — privacy posture and policy

Define `local_fixture`, `internal_test`, `shareable_review` and `formal_dp`
postures. Add a claim registry: only a reviewed provider may emit a DP claim.
Implement baseline indicators for overlap, nearest-neighbor proximity, rare
combinations, uniqueness amplification and direct-identifier leakage.

Policy input includes workspace, source sensitivity, intended use, destination,
provider claims and validation disposition. Default publication is deny unless
policy says otherwise. Add an optional OPA/Rego adapter behind a port. Require
approval for configured high-risk combinations. Persist policy version, decision,
inputs hash and reason.

Negative tests: non-DP claim, special source to public destination, missing
classification, expired approval and attempted publication of a failed report.

## 10. Phase 8 — artifacts and lifecycle

Add plugin-owned tables:

```text
gs_plans gs_profiles gs_runs gs_expectations gs_reports gs_artifacts
gs_approvals gs_exports gs_audit_events
```

Every table is workspace-scoped, indexed by stable ids and migrated through the
Ronin storage port. Store immutable manifests, not mutable output blobs. Files
are written to run-scoped staging, checksummed, verified and atomically
finalized. Add retention metadata, dry-run garbage collection, backup and
reconciliation.

State machine:

```text
DRAFT -> PROFILED -> PLANNED -> GENERATED -> VALIDATED -> APPROVED -> PUBLISHED
any active -> FAILED
GENERATED/VALIDATED -> SUPERSEDED
APPROVED -> REVOKED
```

Transitions are commands with actor, time, prior/new state, command id, reason
and evidence. No route updates state directly. Test duplicate commands, stale
versions, workspace isolation, interrupted finalization, safe GC and restore.

## 11. Phase 9 — extensible format providers

Treat serializers and table formats as two different provider families. CSV,
JSON, JSONL and XML are open-source baseline serializers. Delta, Iceberg and Hudi
are optional table-format providers with their own protocol, metadata, catalog,
snapshot and commit behavior.

Provider manifest:

```json
{
  "format_id":"delta",
  "family":"table",
  "provider_version":"1.0",
  "protocol_versions":["reader_v1","writer_v2"],
  "data_file_formats":["parquet"],
  "features":["acid","snapshots","schema_evolution"],
  "catalogs":["filesystem","rest"],
  "optional_dependencies":["deltalake"],
  "write_atomicity":"optimistic_commit"
}
```

The runtime selects a provider only after checking protocol and dependency
capabilities. It must never simulate a table format by merely writing Parquet
files into a conventionally named directory.

File serializer contract:

```python
validate_destination()
prepare_staging()
write_batches()
flush_and_close()
verify_counts_and_checksums()
publish_atomically()
emit_export_receipt()
```

```python
validate_destination()
prepare_staging()
write_batches()
flush_and_close()
verify_counts_and_checksums()
publish_atomically()
emit_export_receipt()
```

Deliver JSONL, JSON, CSV and XML first, then SQLite. JSONL is UTF-8 with one JSON
value per line. XML declares row elements/namespaces and rejects external
entities. Add Delta, Iceberg and Hudi as separate optional packages, each with a
compatibility matrix, supported protocol versions, catalog modes, schema
evolution rules, partition behavior, snapshot cleanup and reader verification.

Table provider contract:

```text
validate catalog/location and protocol
map logical schema and nullability
write data files to run-scoped staging
create protocol metadata/manifests/log
commit one snapshot/version with idempotency metadata
verify snapshot, schema, counts and history
publish atomically or return partial with cleanup evidence
```

Reject traversal, symlink escapes, duplicate appends and unverified partial
output.

Round-trip tests must read every format and compare schema, nulls, counts and
keys. JSONL must validate UTF-8 and every non-empty line. XML must be tested for
XXE/entity-expansion rejection. SQLite additionally runs `PRAGMA integrity_check`.
Delta/Iceberg/Hudi tests must produce a readable snapshot/version and prove
idempotent retry without duplicate logical output. Unsupported protocol features
must fail before writing data.

## 12. Phase 10 — jobs and resilience

Reuse Ronin `Job -> Run -> Attempt` for `profile`, `plan`, `generate`, `validate`,
`export`, `cleanup` and `reconcile`. Use leases, fencing tokens, cancellation,
bounded retry and run-scoped staging. Emit progress with row/batch counts only.

Failure rules:

| Failure | Required behavior |
|---|---|
| worker dies | reclaim or fail without state corruption |
| lease lost | fenced commit rejected |
| retry after partial export | discard/reuse staging, never blind append |
| missing provider on resume | diagnostic failure, no fallback |
| cancellation | stop at batch boundary and clean staging |
| validation timeout | incomplete, never passed |
| destination unavailable | keep validated artifact, export pending |

## 13. Phase 11 — REST, CLI, SDK and UI

REST:

```text
POST/GET /v1/govern-studio/plans[/{id}]
POST     /v1/govern-studio/plans/{id}/profile
POST     /v1/govern-studio/plans/{id}/compile
POST     /v1/govern-studio/plans/{id}/generate
POST     /v1/govern-studio/runs/{id}/cancel
GET      /v1/govern-studio/runs/{id}
POST     /v1/govern-studio/runs/{id}/validate
GET      /v1/govern-studio/runs/{id}/report
POST     /v1/govern-studio/runs/{id}/approve
POST     /v1/govern-studio/runs/{id}/export
GET      /v1/govern-studio/artifacts/{id}
GET      /v1/govern-studio/providers
GET      /v1/govern-studio/exporters
GET      /v1/govern-studio/formats
```

All mutation routes require idempotency keys and call application services.
CLI commands mirror plan validate, profile, compile, generate, validate, report,
approve and export. SDK namespaces use the same DTOs and error taxonomy.

UI route `/govern-studio` has Scope, Model, Rules, Generate, Validate and Export
steps. It loads the plugin manifest, displays degraded state and evidence links,
disables unavailable providers, redacts diagnostics and never presents preview
as approval. External publication shows exact destination and artifact id.

## 14. Phase 12 — observability and lineage

Metrics:

```text
ronin_govern_runs_total{operation,state}
ronin_govern_run_duration_seconds{operation}
ronin_govern_rows_generated_total{table}
ronin_govern_validation_expectations_total{dimension,status}
ronin_govern_constraint_violations_total{constraint,severity}
ronin_govern_export_bytes_total{format,status}
ronin_govern_policy_decisions_total{decision,reason}
ronin_govern_staging_bytes{workspace}
```

Trace profile, compile, generate, validate, export and policy decision. Use
bounded plan/run/artifact ids, not raw values or unbounded names. Emit
OpenLineage-compatible input/output schema, quality and statistics facets when a
lineage sink is configured.

## 15. Phase 13 — testkit and external proof

Publish a public testkit for manifest, provider registration, seed determinism,
plan compatibility, expectation execution, artifact immutability, lifecycle,
permissions, workspace isolation, exporter round-trip and cancellation.

Create an external example provider in a clean temporary repository using only
public SDK contracts. Install, run, disable and verify removal of capability,
routes, jobs and UI contributions.

## 16. Phase 14 — security and qualification

CI gates: format/lint/typecheck, unit/property/contract tests, import boundaries,
dependency/license/SBOM, secret scan, redaction, provider provenance, sandbox,
traversal/symlink, mutation tests, clean-room install and worker acceptance.

Keep separate evidence for utility, risk indicators, formal DP guarantee (if any),
intended-use disposition, policy and human approval. Never collapse them into a
single privacy score.

## 17. Phase 15 — performance

Benchmark 1k, 100k and 1m rows; 1, 5 and 25 tables; shallow/deep graphs; skewed
categories; high null rates; and 10% reject sampling. Record throughput, peak
memory, bytes, validation time and export time.

The engine must stream batches. Memory growth must follow batch size, not total
output. Preview is bounded and interactive. The compiler enforces row, byte,
CPU, memory and wall-time budgets.

Every provider also declares an estimate function. Before execution the UI shows
expected rows, bytes, peak memory, wall-time range, retry cost and whether the
provider requires a worker. An estimate is not a billing guarantee, but missing
or unbounded estimates block large requests until an operator policy allows them.

## 18. Phase 16 — operations and release

Write runbooks for degraded plugin, provider incompatibility, stuck run, failed
migration, expired profile, constraint exhaustion, validation regression, policy
denial, partial export, corruption, restore, revocation and emergency disable.

Release order:

1. contracts and schemas;
2. deterministic engine and testkit;
3. discovery/UI manifest;
4. profile and compiler;
5. generation/validation jobs;
6. JSONL/CSV;
7. SQLite;
8. external-provider clean room;
9. UI shadow mode;
10. tiny end-to-end smoke;
11. observation window;
12. enable.

Every release receipt includes commit, package hashes, schemas, provider lock,
migrations, tests, smoke evidence and known limitations.

## 19. Issue breakdown

```text
GS-001 canonical contracts and hashing
GS-002 plan schema/parser
GS-003 sample readers/profile evidence
GS-004 relationship graph/compiler
GS-005 built-in generators
GS-006 provider discovery/lock
GS-007 constraint AST/executor
GS-008 expectation registry/report
GS-009 privacy indicators/claims
GS-010 artifact store/lifecycle
GS-011 JSONL/CSV exporters
GS-012 SQLite exporter
GS-013 jobs/lease/cancellation
GS-014 REST/CLI/SDK
GS-015 UI workflow
GS-016 policy/approval
GS-017 telemetry/lineage
GS-018 testkit/clean-room
GS-019 security/performance gates
GS-020 operations/release smoke
```

No issue may bypass plan hashing, state transitions, permission checks, evidence,
artifact verification or cleanup.
