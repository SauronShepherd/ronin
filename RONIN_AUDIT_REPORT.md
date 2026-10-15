# Ronin — Engineering Audit Report

**Repository:** `SauronShepherd/ronin`
**Audited commit range:** `829939c` → `1f40a33` (HEAD moved during the audit; see §2)
**Audit date:** 2026-09-15
**Toolchain:** Python 3.13.14 · ruff 0.16.6 · mypy 1.20.2 · pytest 9.1.1
**Method:** Ronin's own declared gates (`make check` stages) executed locally, plus a source review of
the execution, storage, security, identity and HTTP cores. Every finding below was reproduced by
execution or by direct citation. Nothing is inferred from documentation alone.

Companion task board (same content, browsable): https://claude.ai/artifact/VkgceosD2AVzfRsx9H8KYN

---

## 1. Executive summary

Ronin is a ~36,000-line, 23-package Data + AI platform with a ~22,000-line test suite across 153
files. The engineering substrate is genuinely strong: the test suite is green, the architecture
layering rules are machine-enforced and passing, the authorization and OIDC code is careful, and the
product status ledger (`docs/product/public-v1-status.json`) is more honest about its own gaps than
most released projects.

The problem found at the start of this audit was not the code but the **gate around it**. On
`829939c`, `make check` failed at its first three stages — formatting, linting and type checking —
meaning the command `CONTRIBUTING.md` names as *the* repository gate could not succeed on a clean
checkout. This is a direct consequence of all six CI workflows being parked in
`.github/workflows-disabled/`: nothing had been enforcing the gate, so it drifted.

**During the audit the repository's autonomous builder landed six commits that resolved 13 of the
original 33 findings outright and materially advanced three more.** The measured state improved
substantially — but the same commits also introduced a **failing test on `main`** and left the type
errors untouched, which generated two new findings (T34, T35). This report therefore covers **35
findings**: 13 resolved, 3 partial, 19 open.

The remaining work is narrower and more interesting than the starting position: one red test, type
hygiene, a latent migration-runner defect duplicated 19 times, and cross-language identity risk in
canonical JSON that the existing cross-checker is structurally unable to detect.

### Headline numbers

| Gate | At `829939c` | At `1f40a33` | Change |
|---|---|---|---|
| `pytest` | 866 passed, 9 skipped, **0 failed** | 866 passed, 9 skipped, **1 FAILED** | **regression** |
| `ruff format --check` | **170** files unformatted | **12** | −158 |
| `ruff check` | **682** errors | **157** | −525 |
| `mypy --strict` | **72** errors / 33 files | **72** errors / 33 files | **unchanged** |
| architecture + negative gates | pass | pass | — |
| CI workflows enabled | 0 of 6 | 0 of 6 | — |

Two lines in that table matter most.

**`pytest` has gone red.** The suite was green at `829939c` and is failing at `1f40a33`. The cause is
directly traceable: the builder implemented the canonical-JSON integer bound recommended as T21, and
it is *correct*, but a Hypothesis test with an unbounded integer strategy immediately found the new
boundary. This is now the highest-priority item in the report (§5, **T34**).

**`mypy` did not move at all.** The formatting and lint sweeps cleared 525 lint errors and 158
formatting failures without touching a single type error. Type errors are the part of the gate that
does not yield to automated fixes, and they are the largest *structural* blocker to `make check`.

Both observations point at the same root cause as everything else in this report: **nothing is running
the gate.** A red test suite landed on `main` and went unnoticed.

---

## 2. What changed during the audit

The audit began at `829939c`. Partway through, HEAD advanced to `1f40a33` via five commits:

```
1f40a33 refactor: use shared bundle read limits
c616f8b fix: harden production invariants and lint findings
d372cda style: apply safe lint autofixes
e3c41eb style: format repository sources
ebfd33a docs: advance audit status ledger
        (175 files changed, 2281 insertions, 989 deletions)
```

These overlap heavily with the findings below. All numbers in this report are re-measured against
`1f40a33` unless explicitly marked as the `829939c` baseline. Findings are labelled:

- **RESOLVED** — verified fixed at `1f40a33`
- **PARTIAL** — materially improved, specific remainder identified
- **OPEN** — reproduced at `1f40a33`

One fix deserves specific credit: **T6 was fixed the right way.** The ontology API names were added to
`__all__`, not deleted. The naive reading of that `F401` warning ("unused import — remove it") would
have silently deleted a public API. Whoever made that call read past the tool.

A sixth commit, `24c4779 "fix: close audit correctness and security findings"`, carries the
webhook redirect fix, the security headers and the canonical-JSON integer bound.

### 2.1 Test suite

The suite was green at `829939c` (**866 passed, 9 skipped**, 3m38s) and is **red at `1f40a33`**
(866 passed, 9 skipped, **1 failed**, 3m22s) — see T34. The nine skips are all legitimate
environment gates, not disabled tests:

- 5 × real-Docker acceptance (deferred to the dedicated qualification job)
- 2 × real-Docker integration
- 2 × symlink tests skipped on Windows for lack of `SeCreateSymbolicLinkPrivilege`

Note the last two: `test_local_file_ingestion.py:104` and `test_secret_resolvers.py:56` both verify
**symlink rejection** — a path-traversal defence. On Windows these silently skip, so that security
boundary is unverified on this platform. Worth knowing when reading a green local run.

---

## 3. Architecture assessment

### 3.1 What is well built

These are not filler; they are the parts that should be preserved as-is under any refactor.

- **Enforced layering.** `tools/architecture_gate.py` and `tools/gates_negative.py` encode the
  dependency rules and *prove they fail correctly* — the negative gate constructs deliberate
  violations (`studio_core` importing `studio_server`, `sqlite3` in pure domain code) and asserts they
  are rejected. A gate that tests its own failure mode is rare and valuable.
- **Authorization.** Bearer comparison uses `hmac.compare_digest` (constant-time). Grants are typed
  (`Requirement`/`ResourceScope`/`Action`) and the server refuses to start with an empty grant set.
- **OIDC validation** (`python/studio_security/oidc.py`) is genuinely well done: algorithm allowlist
  restricted to RS256/ES256, mandatory `kid`, rejection of ambiguous key matches, and
  `options={"require": ["exp", "iat", "iss", "sub", "aud"]}`. Network discovery is deliberately
  excluded from the module so the security-critical checks stay testable.
- **Input validation.** Semantic and JDBC identifiers are constrained by
  `^[A-Za-z_][A-Za-z0-9_]*$` at construction; values bind as `?` parameters; `limit` is range-checked
  1..100,000. This is why the two SQL-injection warnings in §6 are false positives.
- **Container security.** The Dockerfile runs `USER 65532:65532` and the entrypoint steps down via
  `gosu`. The `user: "0:0"` in `compose.yaml` is *correct*, not a vulnerability — root is needed only
  to chown a fresh named volume and join the Docker socket group before dropping privilege.
- **SQLite durability.** `WAL` + `synchronous=FULL` + `busy_timeout=5000` + explicit
  `BEGIN IMMEDIATE` is the right configuration for a fenced multi-writer control plane.

### 3.2 Structural weaknesses

- **18 independent schema-version counters** with an undeclared dependency graph (§5, T11).
- **Backend depth vastly exceeds exposed surface**: 23 packages and ~36k LOC behind **6 HTTP routes**
  and a 29-line Studio (§7, T31).
- **`studio_migration` was ungated** until the builder fixed it mid-audit — the package implementing
  the headline `ronin migrate inventory` feature was in neither the mypy nor the coverage list.

---

## 4. Findings — RESOLVED during the audit

| ID | Finding | Evidence of fix at `1f40a33` |
|---|---|---|
| **T1** | 170 files unformatted | `e3c41eb`; now 12 files (PARTIAL, see T1′) |
| **T2** | 682 lint errors | `d372cda`+`c616f8b`; now 157 (PARTIAL, see T2′) |
| **T5** | `studio_migration` excluded from mypy + coverage | now present in both lists in `pyproject.toml` |
| **T6** | Ontology API imported but absent from `__all__` | `ActionExecution` (L169) and `execute_ontology_action` (L216) now exported; verified importable |
| **T13** | Webhook response never closed (socket leak) | `with closing(response)` at `webhook.py:75` |
| **T14** | 8 production `assert`s stripped under `python -O` | **0 remaining** in `python/`; `S101` count now zero |
| **T15** | No HTTP security headers | `_send_security_headers()` at `http.py:448` — `nosniff`, full CSP, `Referrer-Policy`, `X-Frame-Options: DENY`, `Cache-Control: no-store` on API responses |
| **T17** | 7 unused imports | `F401` count now zero — and fixed by exporting, not deleting |
| **T18** | 10 × `BundleReadLimits()` in argument defaults | `1f40a33` "use shared bundle read limits"; `B008` now zero |
| **T24** | README claimed `SECURITY.md` unpublished | claim removed |
| **T25** | Status file listed issue #45 as open | entry removed |
| **T26** | Bug template said reporting route pending | text removed |
| **T28** | 132 `E701`/`E702` in 4 compressed modules | zero remaining after formatting |
| **T30** | Tool caches ignored only by accident | `.venv/`, `.mypy_cache/`, `.ruff_cache/`, `.hypothesis/` now explicit in `.gitignore` |
| **T21** | Canonical JSON accepted unbounded integers | `_MAX_EXACT_INTEGER = 2**53−1` in `canonical_json.py:12` — correct boundary, but see **T34**/**T35** |
| **T12** (half) | Webhook redirect bypassed HTTPS/credential checks | `_RejectRedirects(HTTPRedirectHandler)` + `build_opener` at `webhook.py:20-27`; remainder tracked as **T12′** |

The CSP that landed is exactly the right shape for this application, and it will hold because the
Studio loads only same-origin `./studio.js` and `./studio.css` with no inline script:

```
default-src 'none'; script-src 'self'; style-src 'self';
connect-src 'self'; frame-ancestors 'none'; base-uri 'none'
```

---

## 5. Findings — OPEN

### P0 — Blocking `make check`

#### T34 · Test suite is RED on `main` — Hypothesis found the new integer bound · OPEN · ~5 min · **regression**

**This is the most urgent item in the report.** `main` currently ships a failing test.

The builder implemented T21 (canonical JSON integer bound) in `24c4779`. **The implementation is
correct** — `_MAX_EXACT_INTEGER = (2**53) - 1 = 9007199254740991`, which is exactly
`Number.MAX_SAFE_INTEGER`, the right boundary for cross-language exactness.

But `tests/test_core_ir.py:373` draws params from an **unbounded** `st.integers()`. Hypothesis
probes numeric boundaries by design, so it immediately produced 2⁵³ and the property test died inside
the new validator:

```
tests/test_core_ir.py:373
@given(st.text(min_size=1), st.dictionaries(st.text(min_size=1), st.integers(), max_size=5))
def test_node_id_is_deterministic_for_arbitrary_json_params(...)

  studio_core/ir.py:193  → _node_semantic_payload
  studio_core/ir.py:329  → _canonical_json
  canonical_json.py:20   → ValueError: canonical JSON integers must fit
                            the exact cross-language range

  Falsifying example: instance_key='0', params={'0': 9007199254740992}
                                                       ^ exactly 2**53
```

**Fix.** Bound the strategy to the contract the encoder now enforces — one line:

```python
_JSON_INT = st.integers(min_value=-((2**53) - 1), max_value=(2**53) - 1)

@given(st.text(min_size=1), st.dictionaries(st.text(min_size=1), _JSON_INT, max_size=5))
```

Do **not** relax `_MAX_EXACT_INTEGER` to make the test pass — the bound is the correct behaviour and
the test is now simply asserting something the contract no longer permits.

Also audit `tests/test_t1_properties.py:42`, the only other unbounded `st.integers()` in the suite. It
did not fail here (the values do not reach the canonical encoder), but it is the same latent shape.

**Verify:** `python -m pytest tests/test_core_ir.py -q`

#### T35 · The integer tightening is not recorded in `CHANGELOG.md` · OPEN · ~10 min

`CANONICAL_JSON_V1.md` sets an explicit rule: *"Any change that alters canonical bytes for an input
accepted by v1 is identity-breaking… requires a new explicit identity/schema version, migration rules
for durable resume/idempotency state, updated goldens, and at least one independent checker."*

Rejecting integers that v1 previously accepted **is** a change to what v1 accepts. The precedent is
already set — the duplicate-member/non-finite tightening is recorded in `CHANGELOG.md` under
*"Breaking / compatibility tightening"*. This one is not recorded anywhere.

The good news, verified: **no published golden vector contains an integer beyond 2⁵³−1**, so no
existing identity is invalidated and no migration is required.

```
$ scan tests/golden/canonical_json_v1.json for |int| > 2**53-1
oversize integer literals in goldens: none
```

**Fix.** Add a `CHANGELOG.md` entry under *Breaking / compatibility tightening* stating the new bound
and that no persisted identity changes; add a golden vector at exactly ±(2⁵³−1) and a rejection vector
at 2⁵³ so the boundary is locked by the published contract rather than by one constant in one file.

#### T3 · 72 `mypy --strict` errors across 33 files · OPEN · ~4 h

Unchanged by the formatting and lint sweeps. This is now the primary blocker. Four distinct classes:

```
1. no_implicit_reexport   5 errors   studio_execution → studio_storage   (T7)
2. loop variable reuse   ~12 errors  one name bound to 2-3 types         (T19)
3. redundant-cast          4 errors  studio_storage/{ml,genai}.py
4. missing annotations       —       scheduler_fencing, scheduler_cancellation
   plus: psycopg has no stubs (postgres_core.py:49-50)
```

Also in this set, and worth a real look rather than a mechanical fix:

```
studio_storage/genai.py:162  Argument 6 to "ToolContract" has incompatible type
                             "object"; expected Literal['none','idempotent','non_idempotent']
studio_storage/genai.py:186  Argument 1 to "ToolId" has incompatible type
                             "bool|int|float|str|None|list|dict"; expected "str"
studio_storage/genai.py:138-139  Argument 1 to "tuple" has incompatible type …
```

These are in the JSON→dataclass decode path. The decoded value genuinely is `JSONValue`, and the code
passes it where a `str` or a `Literal` is required **without a runtime check**. Unlike T19, these are
not variable-naming noise — a malformed or hostile `genai_*` row could produce a `ToolId` that is not
a string. Recommend an explicit `isinstance` guard raising `GenAIConflict`, not a `cast`.

> **Do not** reach for `--no-strict` or blanket `type: ignore`. The strictness is the asset.

**Verify:** `mypy python tools packages/pyronin/src docker`

#### T1′ · 12 files still unformatted · OPEN · ~2 min

**Verify:** `ruff format --check python tests tools packages docker`

#### T2′ · 157 lint errors remaining · OPEN · ~1.5 h

```
108  E501   line-too-long        ← incl. the new CSP string at http.py:451
 11  ARG002 unused-method-argument
  9  ARG005 unused-lambda-argument
  6  C401   unnecessary-generator-set
  5  S106   hardcoded-password-func-arg  (tests only — add per-file-ignore)
  1  S105   hardcoded-password-string    (tests only)
  1  F821   undefined-name               (T16)
  1  S110   try-except-pass              (studio_lakehouse/iceberg.py:102)
 …plus 15 further single-instance rules
```

Note `S110` at `studio_lakehouse/iceberg.py:102` — a silent `except: pass`. In a lakehouse table path
a swallowed exception can mean silent data loss; this one deserves reading rather than a `noqa`.

#### T4 · CI remains fully disabled · OPEN · policy decision

All six workflows still in `.github/workflows-disabled/`. The `paths:` filters already reference
`.github/workflows/…`, so a directory rename needs no edits. Recommend enabling **`ci.yml` alone,
on `pull_request` only**, once T3 lands green — the last five commits demonstrate exactly why: good
fixes landed, but nothing verified the gate afterwards, and `mypy` stayed at 72 unnoticed.

---

### P1 — Correctness and hardening

#### T10 · Migration runner splits SQL on `;`, duplicated in 19 modules · OPEN · ~2 h · **latent**

An identical `_execute_script_in_transaction` is copy-pasted verbatim into **19 modules** of
`studio_storage`. Each splits the migration file on a bare semicolon:

```python
for statement in script.split(";"):     # ×19 identical copies
    if statement.strip():
        connection.execute(statement)
```

Safe on today's 24 migration files, which happen to contain no semicolon inside a string literal or
trigger body. It breaks silently the first time anyone writes `CREATE TRIGGER … BEGIN …; …; END;` or
a `DEFAULT ';'` — one statement is split into fragments that then execute or fail mid-transaction.

Affected: `audit`, `catalog`, `connections`, `environments`, `genai`, `ml`, `ontology`, `quality`,
`scheduler`, `scheduler_backfill`, `scheduler_backfill_runtime`, `scheduler_controller`,
`scheduler_events`, `scheduler_execution`, `scheduler_fencing`, `scheduler_leadership`,
`scheduler_schedule`, `sqlite`, `workspaces`.

**Fix.** Extract one shared helper; delete the other 18. Split using the stdlib primitive, not a
regex — accumulate lines and cut where `sqlite3.complete_statement(buffer)` is true. Verified correct
for this case:

```python
>>> sqlite3.complete_statement("INSERT INTO t VALUES(';');")   # True
>>> sqlite3.complete_statement("INSERT INTO t VALUES(';'")     # False
```

`connection.executescript()` is **not** the fix — it issues an implicit COMMIT, which is precisely
why this code is hand-rolled inside `BEGIN IMMEDIATE`.

**Verify:** `grep -rc 'split(";")' python/studio_storage/*.py | grep -v ':0'`

#### T11 · 18 schema-version counters with an implicit dependency DAG · OPEN · ~1 d design

Each domain owns a private `*_schema_migrations` table and its own `migrate_*()`; ordering is
expressed only by these functions calling each other. No cycle detection, no global ordering, no
single answer to "what version is this database?". A partially-applied multi-domain upgrade leaves a
mixed state no counter describes.

Observed edges (excerpt):

```
genai               → catalog          ontology → catalog
audit               → workspaces       quality  → catalog
scheduler_execution → scheduler_fencing
scheduler_events    → scheduler_schedule → scheduler_controller
scheduler_backfill  → scheduler_events
```

**Fix.** Do not rewrite the migrations — the per-domain SQL files are fine and identities are
persisted. Declare the graph as *data*: one registry mapping domain → (migrations, deps), one
topological sort with cycle detection, one transaction spanning the whole upgrade, and a
`ronin migrate status` command. **Land with T10** — both replace the same duplicated function, so
doing them separately means writing it twice.

#### T12′ · Webhook redirect closed; DNS-to-internal-address guard still absent · PARTIAL · ~45 min

The serious half is **fixed**. `_RejectRedirects(HTTPRedirectHandler)` with `build_opener`
(`webhook.py:20-27`) means the validated URL is the only URL contacted, and the `noqa: S310`
justification ("scheme is restricted to HTTPS at construction") is now actually true — at
`829939c` it was not, because `urlopen` followed redirects.

Remaining: no check that the first-hop host resolves to a routable address. A webhook URL of
`https://internal.corp/…`, or one resolving to `169.254.169.254`, still reaches internal services.
`SECURITY.md` names SSRF explicitly in scope.

**Fix.** Resolve the host and reject `is_private / is_loopback / is_link_local / is_reserved`,
reusing the `ipaddress` idiom already proven in `studio_server/transport_policy.py:31`.

#### T7 · Five re-export errors on the scheduler boundary · OPEN · ~20 min

```
scheduler_cron.py:10              "studio_storage.scheduler" does not export "Schedule"
scheduler_bridge.py:17            … does not export "WorkflowRun"
scheduler_schedule_service.py:10  … does not export "Schedule", "WorkspaceId"
scheduler_event_service.py:10     … does not export "WorkspaceId"
```

Same root cause as the now-fixed T6. Before adding names to `__all__`, decide whether `WorkspaceId`
should be re-exported from `studio_storage.scheduler_*` at all, or whether those call sites should
import it from `studio_core` directly — the latter is the cleaner layering and matches the
architecture gate's intent.

#### T19 · Loop-variable reuse defeats narrowing · OPEN · ~30 min · **not a runtime bug**

Traced and confirmed: **runtime behaviour is correct.** One name is rebound to two or three result
types across sequential loops; mypy narrows from the first binding. Clears ~12 of T3's 72 errors.

```
scheduler_daemon.py:169,170,175   result = schedule / event / backfill tick results
bundle_multi_import.py:140,141    definition = Connection… then Environment…
bundle_connection.py:282,283,287  binding/key rebound across kinds
```

Rename to `schedule_result` / `event_result` / `backfill_result`, and
`connection_definition` / `environment_definition`. Do **not** widen annotations to `object` — that
hides the next real error here.

#### T16 · Undefined name in a test annotation · OPEN · ~2 min

```
tests/test_postgres_connector.py:44
    class _Statement:
        def format(self, *args: object) -> _Statement:   # F821
```

Survives only because `from __future__ import annotations` defers evaluation. Quote it, or use
`typing.Self` — which is the more accurate type.

#### T8 · No per-test timeout guard · OPEN · ~15 min

`pytest-timeout` is absent from the dev extra (verified). The suite contains concurrency, leasing,
fencing, leader-election and async-cancellation tests — exactly the categories that fail by *hanging*
rather than asserting. A deadlock regression would hang CI with no indication of which test caused it.

Add `pytest-timeout` to `[project.optional-dependencies].dev`, regenerate
`requirements-dev.lock` with hashes, and set `--timeout=120 --timeout-method=thread` in `addopts`.
Whole suite is ~218s, so 120s per test is generous.

#### T9 · `make mutation` cannot run on non-POSIX hosts · OPEN · ~45 min

Still present. `[tool.mutmut].source_paths = ["src/studio_core"]` — a path that does not exist. The
Makefile compensates by symlinking `python` → `src` at runtime using `ln -s` / `trap` / `rm -f`.

Point `source_paths` at `python/studio_core` and delete the symlink dance. If mutmut cannot accept
that path, record the POSIX-only constraint in `CONTRIBUTING.md` rather than shipping a
silently-broken target in the default `Makefile`.

#### T27′ · Status-file SHA drifted again · PARTIAL · ~5 min + automation

`observed_main_sha` was refreshed to `24c4779` in `ebfd33a` — and is **already 5 commits behind**
`1f40a33`. It is a valid ancestor, so the claim is not false, merely stale.

This is the argument for automating it rather than remembering it. The manual refresh lasted less
than one working session. Add a test asserting `observed_main_sha` is an ancestor of `HEAD` and within
N commits — the file is load-bearing for release claims.

---

### P2 — Canonical JSON: cross-language identity risk

Canonical JSON is the identity substrate — idempotency keys, resume identity, evidence digests and
grant sets all hash these bytes. `CANONICAL_JSON_V1.md` is unusually candid about its own limits, so
none of this is concealed.

**The structural issue:** `tools/canonical_json_check.go` validates *published fixed vectors* and, by
its own admission, "does not claim an independent general algorithm". It therefore confirms what is
already known and is **incapable of detecting T20–T22**. All three were found by execution.

#### T20 · Key ordering unit is unspecified — and is not RFC 8785's · OPEN · ~1 h

The spec says members are "ordered lexicographically by key" without naming the unit. The
implementation uses `sort_keys=True` → **Unicode code point** order. RFC 8785 (JCS) mandates **UTF-16
code unit** order. These agree across the BMP and diverge in the astral planes:

```python
>>> encode({'￿': 1, '\U00010000': 2})
b'{"\xef\xbf\xbf":1,"\xf0\x90\x80\x80":2}'
#   U+FFFF first   ← Ronin (code point)
#   U+10000 first  ← RFC 8785 (UTF-16: D800 DC00 < FFFF)
```

**This is a documentation fix, not a code change.** The bytes are persisted and the versioning rule
correctly forbids changing them. State explicitly that ordering is by Unicode code point and
*deliberately differs from RFC 8785*, so nobody later "corrects" it toward JCS and silently breaks
every stored digest. Add an astral-plane key to the golden vectors to lock it in.

#### T21 · Integers were unbounded — silently corrupted by float64 consumers · **RESOLVED** (with fallout)

The baseline defect at `829939c`:

```python
>>> encode({'n': 2**70})
b'{"n":1180591620717411303424}'     # exceeds 2^53
#   JS JSON.parse reads 1180591620717411300000 → different digest
```

Any consumer parsing JSON numbers as doubles — the browser Studio via `JSON.parse`, or a Go
`interface{}` decode — read a different value. The Go checker could not detect this because it
preserves lexemes via `json.Number`.

**Fixed in `24c4779`** with the correct boundary:

```python
_MAX_EXACT_INTEGER = (2**53) - 1        # == Number.MAX_SAFE_INTEGER
if abs(value) > _MAX_EXACT_INTEGER:
    raise ValueError("canonical JSON integers must fit the exact cross-language range")
```

Two pieces of fallout remain, tracked as **T34** (the resulting red test) and **T35** (the change is
not recorded in `CHANGELOG.md`, contrary to the project's own versioning rule).

#### T22 · Float rendering differs from ECMAScript · OPEN · docs only

```python
>>> encode({'n': 1e16})   # b'{"n":1e+16}'
# JS: JSON.stringify({n:1e16}) → '{"n":10000000000000000}'
>>> encode({'n': 1e21})   # b'{"n":1e+21}'   (JS agrees here)
```

The doc already concedes Python float rendering is "not a language-neutral numeric standard". Promote
the existing guidance ("prefer integers or strings where cross-language equality matters") from prose
to a hard rule for new schemas, and state that no non-Python implementation may recompute v1 identity
over float-bearing payloads.

#### T23 · Make the Go checker adversarial rather than confirmatory · OPEN · ~1 d

`hypothesis` is already a dependency, so the gap is cheap to close. Generate arbitrary valid payloads,
emit them to a file, and have the Go checker re-derive canonical bytes independently and compare
digests. Run as a `make` target. This converts the cross-language claim from a replayed assertion into
an actual differential test — and would have found T20–T22 automatically.

---

### P3 — Hygiene and scope

#### T29 · Studio JS: shadowed identifier, one-statement-per-line style · OPEN · ~1 h

To its credit the DOM code is **safe** — `textContent` everywhere, and the single `innerHTML`
assignment writes a constant string. **No XSS.** But:

```js
// web/studio.js:19
const state = document.createElement("span");
//    ^ shadows the module-level `state` {baseUrl, token, currentJobId}
```

Rename to `stateBadge` and reformat to one statement per line. The token lives in `sessionStorage`,
readable by any script on the origin — acceptable for a local-first alpha, and now genuinely
mitigated by the CSP that landed in T15.

#### T31 · The Studio is 29 lines of JS over 6 endpoints · OPEN · roadmap

```
web/studio.js    29 lines      api/openapi-v1.json   6 paths
web/index.html   50 lines      python/               23 packages, ~36k LOC
```

`PUBLIC_V1_SCOPE.md` describes workspaces, notebooks, catalog, lineage, quality, ML, GenAI, semantic
models and dashboards. The Studio implements a job list, a detail pane, cancel, and a read-only SQL
box.

**The binding constraint on Public v1 is API surface, not domain logic.** Recommend taking one
capability family *all the way* to HTTP + OpenAPI + `pyronin` + Studio rather than adding a ninth
partially-exposed domain package. Catalog search is the strongest candidate: already implemented,
already persisted, read-only.

#### T32 · One static bearer token for the whole server · OPEN · roadmap

The mechanism is sound (constant-time compare, typed grants, fail-closed on empty grant set), but
`RoninHTTPServer` holds exactly one token with one `GrantSet` — no per-user identity on the HTTP path.
Meanwhile `studio_security` already implements OIDC validation, principals, groups and RBAC. The two
are simply not wired together:

```
studio_server/http.py:372   self._token = token         # single credential
studio_security/oidc.py     OidcTokenValidator          # implemented, unused by http.py
```

Connect `authenticate_principal` to the HTTP authorization path and derive the `GrantSet` per
principal; keep the static token as an explicitly-labelled single-user mode.

#### T33 · Semantic models cannot reference a qualified table · OPEN · ~3 h

`SemanticModel.source` is validated by `_identifier()` → `^[A-Za-z_][A-Za-z0-9_]*$`. Safe against
injection, but makes `schema.table` and `catalog.schema.table` unrepresentable — which every real
lakehouse source uses. Invisible today because only the single-table path is wired up.

Model `source` as a **tuple of validated parts**, keeping each part under the existing rule and
joining with quoted separators in `compile_metric_query`. Do not relax the regex to permit dots —
that is how identifier validation regresses into injection.

---

## 6. Explicit non-findings

Recorded so they are not "fixed" pointlessly in a later pass.

| Flagged as | Reality |
|---|---|
| `S608` SQL injection at `studio_semantic/compiler.py:79` | **False positive.** Identifiers pass `_identifier()` regex; values bind as `?`; `limit` range-checked 1..100,000. |
| `S608` SQL injection at `studio_connectors/jdbc.py:120` | **False positive.** Same pattern — `self._identifier()` on schema/table/column. |
| `user: "0:0"` in `compose.yaml` | **Correct, not a vulnerability.** Root is needed to chown a fresh named volume and join the Docker socket group; the entrypoint then drops to 65532 via `gosu`. |
| `innerHTML` in `web/studio.js:12` | **Safe.** Writes a constant string; all dynamic content uses `textContent`. |
| T19 loop-variable mypy errors | **Not runtime bugs.** Traced; behaviour is correct. Type noise only. |
| `B008` mutable default (now fixed anyway) | Was harmless — `BundleReadLimits` is a frozen dataclass. |

Add targeted `noqa` comments **naming the validating function** for the two `S608` cases, so the
suppression carries its own justification.

---

## 7. Recommended sequence

Dependencies matter more than priorities here.

0. **T34 — first, today.** `main` is red. One line bounds the Hypothesis strategy. Everything else in
   this list is easier to verify once the suite is green again.
1. **T35, T1′** — record the integer tightening in `CHANGELOG.md` and add the boundary goldens;
   format the remaining 12 files (together, ~15 min).
2. **T3 + T7 + T19** — the type-error block, in that order. T7 and T19 together clear ~17 of the 72;
   the `genai.py` decode errors need real judgement, not casts. **This is the critical path** —
   `make check` cannot pass without it.
3. **T2′** — remaining lint, in rule-sized commits. Add per-file-ignores for the tests-only
   `S105`/`S106`, and *read* the `S110` in `iceberg.py` rather than suppressing it.
4. **T16, T8, T9** — small permanent widenings of the safety net.
5. **T10 + T11 together** — they replace the same duplicated function.
6. **T12′** — close the SSRF remainder.
7. **T4** — enable `ci.yml` on `pull_request` once the gate is green. Do this as soon as step 3
   lands; the last five commits show what happens without it.
8. **T27′** — automate the SHA-freshness check rather than refreshing it by hand again.
9. **T20–T23** — canonical JSON documentation and the differential checker.
10. **T29, T31–T33** — hygiene and scope increments.

---

## 8. Closing assessment

The failing gates at `829939c` read as drift from a period of rapid generated construction, not as
neglect — and the five commits that landed mid-audit support that reading: once attention was on it,
158 formatting failures and 525 lint errors cleared quickly and correctly.

Three things distinguish this repository from most projects at a comparable stage: the architecture
gate tests its own failure modes, the product status ledger classifies capability families honestly
rather than optimistically, and `CANONICAL_JSON_V1.md` documents the limits of its own identity claims
instead of overstating them. That last one is why the canonical-JSON findings in §5 are framed as
under-specification rather than deception.

The substantive remaining risks are narrow and specific: **72 type errors** that no automated sweep
will clear, **one latent migration defect duplicated 19 times**, and **a cross-language identity
checker structurally unable to detect the divergences it exists to catch**. None require
architectural change. All are tractable.

But the clearest evidence in this report is what happened *during* it. In five commits the builder
cleared 525 lint errors, hardened the webhook against redirect-based SSRF, added a correct CSP,
removed every production `assert`, and implemented a correct cross-language integer bound — genuinely
good work. It also shipped a **failing test to `main`** and left `mypy` at exactly 72, and neither was
noticed, because no gate ran.

So the one process recommendation outranks every individual fix: **re-enable `ci.yml`.** Every finding
in this report — the original 33 and the two new ones it generated — is a consequence of a good gate
that nothing was running.

---

### Appendix — reproducing these results

```bash
python -m venv .venv && . .venv/Scripts/activate
python -m pip install --require-hashes -r requirements-dev.lock
python -m pip install -e . --no-deps

ruff format --check python tests tools packages docker
ruff check python tests tools packages docker --statistics
mypy python tools packages/pyronin/src docker
python -m tools.architecture_gate python
python -m tools.gates_negative
python -m pytest -q -p no:randomly
```
