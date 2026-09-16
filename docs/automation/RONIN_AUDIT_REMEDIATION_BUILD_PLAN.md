# Ronin Engineering Audit Remediation Build Plan

**Repository:** `SauronShepherd/ronin`  
**Evidence source:** `RONIN_AUDIT_REPORT.md`, audited through commit `1f40a33`  
**Plan language:** English  
**Plan status:** proposed execution plan; findings are evidence, not executable instructions

## 1. Objective and operating rules

Restore a trustworthy Public v1 engineering gate, fix every confirmed defect in the 35-finding
audit, widen static-analysis coverage, and preserve the repository's fail-closed and
provider-neutral design. The final state must be reproducible from a clean checkout and must not
claim release readiness while maintainer-controlled CI, provider certification, security review,
or production qualification remain unavailable.

The audit text is treated as an engineering input. Commands appearing in it are candidate
verification commands, not authorization to change CI policy, publish releases, contact providers,
or alter external repository settings. Every implementation change must have a focused regression
test or a documented reason why the existing gate is sufficient.

## 2. Baseline and acceptance criteria

Record before each phase:

```text
git rev-parse HEAD
python --version
python -m pytest -q
python -m ruff format --check python tests tools packages docker
python -m ruff check python tests tools packages docker --statistics
python -m mypy python tools packages/pyronin/src docker
python -m tools.architecture_gate
```

The remediation is complete only when all of the following are true:

1. `make check` reaches and passes every enabled stage on a clean checkout.
2. No test is red; intentionally unavailable host/provider tests remain explicitly skipped with
   actionable reasons.
3. Ruff format is clean and Ruff check has no unreviewed findings.
4. Strict mypy is clean for every declared package, including `studio_migration`.
5. Architecture and negative architecture gates pass.
6. Canonical JSON vectors, the Go checker, and any differential cross-language check agree.
7. Security-sensitive paths have regression coverage, particularly redirect/SSRF prevention,
   HTTP headers, credential handling, and optimized (`python -O`) execution.
8. Status, changelog, README, issue templates, and release documents describe the actual state.
9. CI re-enablement is performed only after maintainer authorization and only for workflows whose
   evidence and external prerequisites are satisfied.

## 3. Dependency-aware delivery order

| Phase | Scope | Exit gate | Depends on |
|---|---|---|---|
| A | Stop-the-line regression and documentation | T34/T35 green and recorded | none |
| B | Restore formatter and safe lint baseline | format clean; safe Ruff fixes committed | A |
| C | Strict typing and public exports | mypy clean; import contracts tested | B |
| D | Runtime correctness and security hardening | focused security/storage suites green | A, C |
| E | Migration schema and cross-language identity | canonical differential checks green | A, C |
| F | CI and contributor gate | authorized CI check passes on clean checkout | B–E |
| G | Remaining product-surface work | capability-specific end-to-end evidence | F |

Use small, single-purpose commits for mechanical or security-sensitive changes. Do not combine
formatter churn with behavioral changes. Add each commit to `.git-blame-ignore-revs` only if the
repository adopts that file and the maintainer approves it.

## 4. Phase A — stop the line: T34 and T35

### A1. Fix the red property test (T34, P0)

**Finding:** `tests/test_core_ir.py` uses an unbounded Hypothesis integer strategy. The newly
enforced canonical integer limit correctly rejects `2**53`, causing `main` to fail.

Implementation:

1. Locate the parameter strategy that generates IR values in `tests/test_core_ir.py`.
2. Replace only the integer strategy with `st.integers(min_value=-(2**53 - 1), max_value=2**53 - 1)`.
3. Preserve all other generated-value coverage.
4. Add one explicit boundary example for `-(2**53 - 1)` and `2**53 - 1`.
5. Add one explicit rejection test for `2**53` and `-(2**53)` at the canonical boundary.
6. Run the property test repeatedly and with the repository's normal randomization settings.

Verification:

```text
python -m pytest tests/test_core_ir.py tests/test_canonical_json.py -q
python -m pytest -q
```

### A2. Record the identity tightening (T35, P0)

1. Add a `CHANGELOG.md` entry under an unreleased compatibility/security section.
2. State that canonical v1 encoding now rejects integers outside the exact JavaScript/IEEE-754
   safe-integer range, and that existing goldens were checked for compliance.
3. Document the compatibility consequence: callers must use strings for larger identifiers or
   values requiring arbitrary precision.
4. Preserve the updated canonical goldens and add both numeric boundary cases.
5. Run a repository search for persisted numeric literals outside the new range in fixtures,
   examples, migrations, and checked-in state. Record the result in the changelog or audit note.

## 5. Phase B — restore format and lint hygiene

### B1. Formatting sweep (T1, already mechanically started)

1. Run `ruff format python tests tools packages docker` in one isolated commit.
2. Confirm no generated files, build outputs, qualification evidence, or package caches are staged.
3. Verify `ruff format --check` reports zero files requiring changes.

### B2. Safe Ruff autofixes (T2)

1. Run `ruff check python tests tools packages docker --fix` after formatting.
2. Review every changed import, simplification, and deprecated-import replacement.
3. Commit safe autofixes separately from hand edits.
4. Recompute the rule breakdown and retain the report as build evidence.

### B3. Hand-fix remaining rules by group

Work in this order, with one focused test/lint run per group:

1. `E501`, `E701`, `E702`: split long and compressed statements, prioritizing
   `studio_core/{genai,ml}.py` and `studio_storage/{genai,ml}.py`.
2. `I001`, `F401`, `UP*`, `C4*`, `SIM*`: keep public re-exports intact and remove only truly
   unused imports.
3. `ARG001`, `ARG002`, `ARG005`: rename intentionally unused arguments with the project's
   accepted convention or use a justified protocol-compatible suppression.
4. `PT011`, `PT017`, `PT018`: make pytest assertions specific without weakening test intent.
5. `S101`: replace production asserts with explicit domain errors; retain test asserts only under
   the existing test-only policy.
6. `S105`, `S106`: replace test literals with clearly synthetic values or targeted suppressions.
7. `S608`, `S310`: suppress only after proving identifier validation/parameter binding or URL
   scheme enforcement on the same line; include the validating function in the comment.
8. `PTH105`, `S110`, and remaining one-off rules: fix behaviorally, not by blanket ignores.

After each group, run the narrowest affected tests and then the complete Ruff command. Do not
declare the gate restored until `make check` itself passes.

## 6. Phase C — strict typing and export contracts

### C1. Coverage and mypy scope (T5)

1. Keep `studio_migration` in both `[tool.mypy].packages` and `[tool.coverage.run].source`.
2. Add a scope-regression test that compares on-disk `studio_*` packages with both configuration
   lists.
3. Run strict mypy and coverage with the package included.

### C2. Public exports (T6, T7)

1. Export `ActionExecution` and `execute_ontology_action` from `studio_core.__all__`.
2. Add explicit public-import tests for every newly supported API.
3. Decide whether `WorkspaceId` belongs in `studio_storage` public exports; prefer importing it
   from its canonical defining layer if that preserves architecture.
4. Add explicit `__all__` exports for `Schedule` and `WorkflowRun` where downstream modules rely
   on them.
5. Run `mypy -p studio_core -p studio_execution -p studio_storage` and the architecture gate.

### C3. Strict-mypy error classes (T3, T19)

1. Rename reused loop variables in scheduler and Bundle modules so mypy narrowing remains valid.
2. Remove redundant casts only where the inferred type is verified.
3. Add missing annotations to scheduler cancellation/fencing helpers.
4. Handle optional `psycopg` stubs with a narrowly scoped documented configuration or protocol,
   never a global strictness relaxation.
5. Re-run strict mypy over all configured packages and publish the exact error count.

## 7. Phase D — runtime correctness and security

### D1. Migration SQL execution (T10)

1. Inventory all duplicated `script.split(";")` implementations.
2. Create one storage-layer helper that accumulates SQL and uses
   `sqlite3.complete_statement()` to identify complete statements.
3. Preserve transaction ownership; do not replace the helper with `executescript()`.
4. Migrate all 19 callers without changing migration ordering or persisted schema identities.
5. Add tests for semicolons in string literals, trigger bodies, comments, incomplete statements,
   rollback, and multi-statement transactions.
6. Run every storage migration test and a fresh-database migration smoke test.

### D2. Migration schema registry (T11)

1. Define a registry of domain, migration list, and explicit dependencies.
2. Implement deterministic topological sorting with duplicate, missing-dependency, and cycle
   detection.
3. Preserve each domain migration identity while making ordering inspectable.
4. Define transaction boundaries explicitly and test partial-failure recovery.
5. Add `ronin migrate status` showing every domain and version.
6. Add compatibility tests for existing databases at each known domain version.

### D3. Webhook SSRF and resource safety (T12, T13)

1. Keep HTTPS-only and embedded-credential rejection.
2. Use an opener/redirect handler that refuses every redirect.
3. Resolve and reject loopback, private, link-local, reserved, and unspecified destinations,
   including IPv6; define DNS-rebinding limitations explicitly.
4. Close every response object using a context manager compatible with injected test transports.
5. Add tests for redirects to HTTP, loopback, metadata/link-local addresses, invalid host forms,
   oversized responses, non-2xx responses, and response closure.
6. Run security and webhook tests under normal and optimized Python execution where applicable.

### D4. HTTP security headers (T15)

1. Centralize response security headers for JSON API and Studio asset responses.
2. Add `nosniff`, CSP, frame denial, referrer policy, and API `Cache-Control: no-store`.
3. Verify CSP matches the actual same-origin Studio asset loading behavior.
4. Add HTTP tests that inspect both success and error responses, including `/studio` assets and
   evidence/status endpoints.

## 8. Phase E — identity and cross-language verification

### E1. Canonical JSON contract (T20–T22)

1. Document that v1 key ordering is Unicode code-point ordering and intentionally differs from RFC
   8785/JCS; do not silently change persisted bytes.
2. Add an astral-plane/BMP ordering golden.
3. Document the exact-integer bound and the non-language-neutral float limitation.
4. Require strings for new schemas where values exceed the exact numeric range or where
   cross-language identity depends on decimal rendering.
5. Keep the versioning and compatibility policy explicit in `CANONICAL_JSON_V1.md`.

### E2. Differential Go checker (T23)

1. Define a shared bounded payload generator for valid canonical values.
2. Emit deterministic generated cases from Python, including Unicode keys, boundaries, nested
   structures, negative zero, and supported floats.
3. Make the Go checker independently derive canonical bytes and compare both bytes and digests.
4. Add a Make target that runs the generator and Go checker without relying solely on published
   vectors.
5. Store failing counterexamples as minimized fixtures.
6. Ensure the checker fails when Python and Go ordering, number, escaping, or duplicate-member
   behavior diverges.

## 9. Phase F — CI, release, and documentation truth

### F1. Re-enable the contributor gate (T4)

1. Do not rename `.github/workflows-disabled` until T34 and the full local gate are green.
2. Obtain maintainer authorization to enable `ci.yml` on pull requests only.
3. Verify path filters, pinned actions, Python versions, dependency installation, and artifact
   retention.
4. Keep Docker qualification, publish, release, and security workflows parked until their
   external evidence and policy prerequisites are approved.
5. Update the status ledger only after the workflow executes successfully on the exact candidate.

### F2. Documentation consistency (T24–T27, T30)

1. Keep README and `SECURITY.md` consistent about the private reporting route; do not claim the
   route is verified unless repository settings and the reporter path were actually checked.
2. Remove resolved issue #45 from human decisions only when the route is confirmed active.
3. Point the bug template to `SECURITY.md` and the repository vulnerability-reporting action.
4. Update `observed_main_sha` and `observed_at` whenever the status ledger is changed; add a test
   that rejects excessive drift from HEAD.
5. Ignore `.venv`, `.mypy_cache`, `.ruff_cache`, `.hypothesis`, build outputs, and local evidence
   explicitly.

## 10. Phase G — scoped product increments

These are roadmap items, not defects to conceal behind green lint:

1. Extend the Studio/API/SDK surface from jobs and SQL to one complete capability family, with
   catalog search as the first candidate.
2. Integrate OIDC principal authentication into HTTP authorization while retaining static bearer
   auth as explicitly labelled single-user mode.
3. Add qualified-table semantic model sources as validated identifier tuples, never by relaxing
   the identifier regex to permit unsafe interpolation.
4. Integrate durable scheduler branch decisions and skipped-task persistence behind the tested
   branch contract.
5. Extend Bundle support to the next canonical executable metadata family only after identity and
   atomic-commit contracts are available.

## 11. Verification matrix

| Area | Required evidence |
|---|---|
| Regression | T34 boundary/property tests and full pytest |
| Formatting | `ruff format --check` with zero changes |
| Lint | `ruff check` zero unreviewed findings and a saved rule report |
| Types | strict mypy for all configured packages |
| Architecture | positive and negative architecture gates |
| Storage | fresh DB migration, semicolon/trigger fixtures, rollback tests |
| Security | webhook SSRF/redirect/closure tests; HTTP header tests; optimized execution |
| Identity | updated goldens, Python/Go differential cases, digest agreement |
| CI | authorized pull-request workflow on exact HEAD |
| Documentation | status SHA/drift test; changelog and security-route consistency |
| Product scope | end-to-end HTTP/OpenAPI/SDK/Studio evidence for each claimed family |

## 12. Definition of done and reporting format

Every completed task report must include:

```text
Finding IDs addressed:
Files changed:
Behavioral change:
Tests and exact results:
Static checks and exact results:
External prerequisites still pending:
Verified completion percentage:
```

Completion percentage must be based on verified deliverables, not the number of edited files or
passing unit tests. A green local suite does not close provider certification, CI authorization,
legal/security review, PostgreSQL HA, Kubernetes production qualification, or any other
maintainer-controlled requirement.
