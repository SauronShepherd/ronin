# Ronin Public v1 release decision checklist

**Decision:** NO-GO / release not qualified

**Last evidence review:** 10 November 2026

**Candidate SHA:** runtime/test candidate `817ae3c93d61cd22a44f28f2c37090ba22573108`; the current candidate-bound technical receipts are recorded below. Release paperwork is not yet approved and the canonical worktree retains unrelated user-owned artifacts.

**Qualification progress:** 0/13 Public v1 capability families
**Launch guidance:** delay the public release until all mandatory rows below are closed on one clean candidate.

This checklist is the short decision sheet for
[`PLAN_FINAL_RONIN_RELEASE_2026-11-03.md`](PLAN_FINAL_RONIN_RELEASE_2026-11-03.md).
Historical test passes from earlier SHAs or dirty worktrees are diagnostic
context only. Do not combine results across commits to produce a GO decision.
The machine-readable ledger at `public-v1-status.json` links here. When its
qualification status is `blocked`, `tools/capability_status.py` requires a
non-empty set of uniquely identified blocking conditions, each with a valid
status, explanation and evidence reference. A mere pending test is represented
as `qualification_pending`; independent human and candidate blockers remain
explicit rather than being collapsed into that test status.

## 10 November exact-candidate qualification — current `817ae3c`

The candidate adds explicit Environments and Deployments decision workbenches:
Environments exposes Observe/Author/Govern with deterministic diff and pause/restore;
Deployments exposes Observe/Bind/Operate with the validated bindings-array contract.
The complete static Chromium suite passes `147/147`; the web audit passes with
`71` files, `38` modules, `180` route invocations and `0` failures; the ratcheted
delivery budget is `2,123,786` asset bytes, `70` requests, `36` modules,
`15` stylesheets and `5,778` HTML bytes. The focused workbench, responsive and
accessibility journeys pass.

Candidate-bound technical receipts:

- Python/PostgreSQL: `4563/4590` passed, `27` explicit environment/provider/POSIX
  skips and `0` failures. The authoritative rerun receipt is
  `%TEMP%\\ronin-python-full-817ae3c-rerun-20261110`; an earlier infrastructure
  abort with exit `-1` produced no JUnit and is not counted as a test result.
- Docker: `27/27` passed, strict v0.1 `15/15`, `0` skips/failures; runtime image
  `sha256:05bdec5e2d217f1208dd755332408da54795920feb66862a687fe76b4dbf9505`.
- Helm/kind: lint, Secret boundary, install, readiness, health, Studio/API,
  durable job, restart persistence and cleanup passed; receipt
  `%TEMP%\\ronin-helm-a4d982b-20261110`.
- Live UI/API: `33/33` Playwright cases across 25 routes (24 API-backed), 250
  correlated events, `0` server/network errors and `0` unexpected auth gaps;
  receipt `%TEMP%\\ronin-live-a4d982b-20261110`.
- Installed artifacts: `90/90`; wheel SHA-256
  `30e2c40517e8ef0bd3c17abd074ff2b0fdedff62a2c804d87dc325d967af3bcf`, sdist
  SHA-256 `51152a21b86235c173d2a3a738faf15b3e7fe7c84d31de93e87227fa399763b2`.
- Supply chain: exact artifact identity, application/runtime/probe CycloneDX,
  provenance and container inventory validate with `supply_chain_evidence.py`;
  Trivy is pinned to `0.76.1`, with raw runtime/probe SBOMs and zero secrets.
- VEX: Docker Scout `1.27.0` finds `3` raw findings and `0` after the exact
  two-product OpenVEX binding for both runtime and probe; both verifiers pass.
- Floci: endpoint HTTP 200; Terraform `1.13.5`, AWS provider `6.65.0`,
  plan/apply/refresh/destroy/state-list all return zero and fixture resources
  are absent after destroy; receipt `%TEMP%\\ronin-floci-74fb533-evidence-20261110`.

The remaining license qualification is intentionally not presented as green:
22 dependency review decisions are missing, one stale `pyyaml==6.0.3` policy
entry remains, and 9 inventory/policy evidence records are mismatched. Release
remains **NO-GO** at `0/13` families, with security/legal/NOTICE/claims, manual
visual, rollback/support, provider/toolchain, license-policy and governance
approvals still open.

## 9 November exact-candidate refresh — historical `4962ff05`

That historical clean runtime/test candidate was `4962ff0512956f0214ddc9a96def9ae2fd77ccfa`.
Runs now follows the global Studio context: launch context seeds the project
filter and changing context refreshes the scoped query. The Studio shell now exposes a visible command affordance, workbenches use
guided decision modes, all runtime styles are packaged, installed-route
smoke/accessibility contracts are synchronized, and unavailable-server UI no
longer exposes internal URLs. Exact local qualification is green: Python/
PostgreSQL `4563 passed, 27 skipped, 0 failed` of `4590` on the unchanged parent;
Chromium `138/138`; web audit `69` files, `38` modules, `180` route invocations,
`0` failures; budget `2,101,245` asset bytes, `68` requests, `36` modules, `13` stylesheets
and `5,639` HTML bytes; installed artifacts `90/90` with wheel
`8a962e13c6a303a84048889302f720c293a7d8a14f108bf73fef89b01754bd05` and sdist
`832b5073fd050093f4e5ea50e11fb4d2687dcdbe80c21d4fc8b9adc91cf47caa`.
Docker is `27/27` plus strict v0.1 `15/15` on image
`sha256:da112fd1ba92f131668dc94f22a37829c5f2c641c29bba9901f17fc50ede83f4`;
Helm/kind and persistence pass; live qualification is `33/33` over 25 routes,
with 246 correlated events and no server/network errors. Docker Scout `1.27.0`
now reports `3` raw findings and `0` after digest-bound OpenVEX. Trivy `0.76.1`
reports `0` secrets and one `MEDIUM` `CVE-2026-4738` in each exact image
(`zlib 1.3.2-r1`, fixed upstream at `1.4-r0`). The VEX binds runtime
`sha256:da112fd1ba92f131668dc94f22a37829c5f2c641c29bba9901f17fc50ede83f4`
and probe
`sha256:84430cb0fa577d1bff12182fa725316402a4e6500c4d0d6ed070242a76980099`.
The security reviewer has not accepted the VEX statements or zlib exception.
The exact CycloneDX application/runtime/probe inventories, provenance and
fail-closed supply-chain validator pass; policy reviews remain missing/stale
and are not being silently accepted. Release remains **NO-GO** at `0/13`
families: provider/credential, security/VEX finding triage, legal/NOTICE/claims,
visual, rollback/support, full provider/toolchain matrix, license policy and
governance gates remain open.

The candidate-bound Cloud Studio/Floci lane also passes with Floci `2.1.0`
digest-pinned, AWS provider `6.65.0` and official-checksummed Terraform
`1.13.5`: plan/apply/refresh/destroy/state-list all returned zero, synthetic
S3/SQS resources were observed after apply, and both Terraform state and
Floci resources were empty after destroy. Receipt:
`%TEMP%\\ronin-floci-4962ff0-20261109-c81f\\qualification.json`.

Receipts: `%TEMP%\\ronin-python-full-b86a0f6-20261109` (unchanged parent),
`%TEMP%\\ronin-docker-4962ff0-20261109b`, `%TEMP%\\ronin-helm-4962ff0-20261109b`,
`%TEMP%\\ronin-live-4962ff0-20261109`,
`%TEMP%\\ronin-artifact-qualification-4962ff0-20261109.json`.
Its image digest, Docker/Helm/live, package, Trivy, VEX,
SBOM/provenance, supply-chain and Floci receipts are exact for this application
candidate. Technical gates are green; release approval remains blocked by the
explicit family, human, legal, support and operational gates above.

Exact supply-chain receipts: `%TEMP%\\ronin-vex-4962ff0-20261109-clean`,
`%TEMP%\\ronin-trivy-4962ff0-20261109`,
`%TEMP%\\ronin-supply-chain-4962ff0-20261109-f1209095dc27445e851f92a09136226d`.

The previous table is retained as historical evidence for runtime `8a85586`.
For that historical candidate, the application lanes were technically qualified;
the family ledger remains `0/13`, and human security, legal/NOTICE/claims,
license policy, visual product, rollback, support and governance approvals
remain open.

## 9 November exact-candidate refresh — historical `4157181`

The historical runtime/test candidate was `4157181843d47893e77d62bed62fdafeb31d6f0b`,
the tenth UI pass after the backend candidate `8a855866`. Projects now exposes
Author/Connect/Operate/Govern decision modes plus an operational brief with
source posture, next gate and a secret-safe Source column, while the connection
dialog opens deterministically during fast bootstrap. The exact UI lane passes
Chromium `132/132`; web audit reports `68` files with zero failures and the
measured budget is `2,088,109` asset bytes, `67` requests, `36` modules, `12` stylesheets and
`5,299` HTML bytes. Installed PyRonin artifacts pass `90/90` with wheel digest
`5cf92538ee70f1631bd13c5dcc79cf8a2321cbbbdf2adaea9c4c693b6df9ce8c` and sdist
digest `6873d4d3748e7d1d9a4fbf7cf59a9bdccb0d459ae73bb396dba6c0382a110b24`.
Docker passes `27/27` plus strict v0.1 `15/15` on image
`sha256:af76b755b4bf64ef17f1a670d7b35e1e099f8cd8b26b808194446fb30be6755e`;
Helm/kind passes with cleanup; live passes `33/33` across 25 routes with 247
correlated events; Docker Scout/OpenVEX is `3 raw / 0 applied` for that exact
image. The backend Python/PostgreSQL receipt remains green on unchanged source
code: `4562 passed, 27 skipped, 0 failed` of `4589`; coverage passes `53/53`
and `62/62`. No release GO is claimed while any human or family gate remains
open.

The release remains **NO-GO**: the 13-family ledger is 0/13, the VEX requires
security-reviewer acceptance, Trivy/container SBOM is unavailable, and
maintainer/legal/product, provider, rollback, support-matrix, governance and
manual visual decisions remain open.

The exact historical receipts are `%TEMP%\\ronin-helm-4157181-20261109b`,
`%TEMP%\\ronin-live-4157181-20261109c`, `%TEMP%\\ronin-vex-4157181-20261109b`,
`%TEMP%\\ronin-artifact-identity-4157181-release.json`,
`%TEMP%\\ronin-release-sbom-4157181.json`,
`%TEMP%\\ronin-release-provenance-4157181.json` and
`%TEMP%\\ronin-supply-chain-4157181.json`. A first live attempt timed out while
seeding Kafka and was discarded after successful cleanup; the fresh rerun is the
33/33 receipt above.

### Historical candidate-bound UI follow-up — runtime `6279ef7`

The previous runtime/test candidate was `6279ef792d41a78a6e022f8193ed70bcf5ff7fc3`,
the UI-only sixth pass after the backend candidate `8a855866`. The exact UI lane
passes Chromium `130/130`; web audit reports `64` files with zero failures and
the measured budget is `2,059,874` asset bytes, `63` requests, `35` modules,
`9` stylesheets and `5,050` HTML bytes. Ingestion's Discover/Preview/Sync/Observe
decision workbench is covered by focused, accessibility, responsive and full
static tests. The current installed PyRonin artifacts pass `90/90` with wheel
digest `aa8db3bc80c8356b2a05821655a58a14e8b86a46f9b1d15eab2a1311e70cbdda` and
sdist digest `4ba0f8c5c92a29fcd87b9d18ba838412f080324bb0a718bb5ea30a85596ecc6d`.
Docker passes `27/27` plus strict v0.1 `15/15` on image
`sha256:a6771cf1fa7dee4566f6fc298ea89d23ddf31c61233d5e25c3daac985c3e1aca`;
Helm/kind passes with cleanup; live passes `33/33` across 25 routes with 252
correlated events; Docker Scout/OpenVEX is `3 raw / 0 applied` for that exact
image. The backend Python/PostgreSQL receipt remains green on unchanged source
code: `4562 passed, 27 skipped, 0 failed` of `4589`; coverage passes `53/53`
and `62/62`. No release GO is claimed while any human or family gate remains
open.

The release remains **NO-GO**: the 13-family ledger is 0/13, the VEX requires
security-reviewer acceptance, Trivy/container SBOM is unavailable, and
maintainer/legal/product, provider, rollback, support-matrix, governance and
manual visual decisions remain open.

### Candidate-bound UI follow-up — runtime `6279ef7`

This candidate changes only the web surface, its web regression and the measured
static budget relative to `8a85586`; no Python or backend runtime file changed.
The clean checkout `C:\Users\angel.alvarez\AppData\Local\Temp\ronin-release-6279ef7`
therefore reuses the unchanged backend receipt while binding the delivered UI
to a new image and live qualification:

- Static UI: Chromium `130/130`; audit `64` files, `37` modules, `180` route
  invocations, `0` failures; budget `2,059,874` bytes, `63` requests,
  `35` modules, `9` stylesheets and `5,050` HTML bytes.
- Artifact qualification: `90/90`; wheel
  `aa8db3bc80c8356b2a05821655a58a14e8b86a46f9b1d15eab2a1311e70cbdda`, sdist
  `4ba0f8c5c92a29fcd87b9d18ba838412f080324bb0a718bb5ea30a85596ecc6d`.
- Docker: `27/27`, strict v0.1 `15/15`, no skips/failures; image
  `sha256:a6771cf1fa7dee4566f6fc298ea89d23ddf31c61233d5e25c3daac985c3e1aca`.
- Helm/kind: lint, Secret boundary, isolated cluster, image load, install,
  readiness, health, Studio/API, queued-job persistence, restart and cleanup.
- Live: `33/33`, 25 active routes, 24 API-backed, 252 correlated events
  (`237` OK, `15` expected WARN), 0 server/network errors and 0 unexpected
  authorization gaps.
- VEX: Docker Scout `1.27.0`, `3` raw and `0` after the exact digest-bound
  OpenVEX; security reviewer acceptance is still required. Trivy remains
  unavailable, so no container SBOM inventory is claimed.
- SDK supply chain: artifact identity, CycloneDX SBOM, provenance and digest
  summary verify for `6279ef7`; container inventory is still empty.

These receipts qualify the current UI/image candidate technically in the
available lanes; they do not close the release-family or human decision ledger.

The previous runtime/test candidate `6012ed52deb5b5a449abc73944cd21293ac06d33`
has exact local technical receipts: static Chromium `128/128`; Python/PostgreSQL
`4562 passed, 27 skipped, 0 failed` of `4589`; Docker `27/27` with strict v0.1
`15/15`; Helm/kind fully passed with isolated cleanup; live `33/33` over 25
active routes with 247 correlated events; and Docker Scout/OpenVEX `3 raw / 0
applied` against runtime image
`sha256:89b122401876ff1b82f06b9e1f20dab3fa077981fb9bf51e264d3bd00d5b6be0`.
The installed PyRonin artifact qualification passed `90/90`; wheel and sdist
digests are recorded in the build plan. Gitleaks found no leaks in tree/history,
pip-audit found no known vulnerabilities in test/runtime/bootstrap, and the
SDK CycloneDX SBOM plus provenance passed generation and verification.
Receipts: `%TEMP%\\ronin-python-full-6012ed5-20261108`,
`%TEMP%\\ronin-docker-6012ed5-20261108`,
`%TEMP%\\ronin-helm-6012ed5-20261108`,
`%TEMP%\\ronin-live-6012ed5-20261108`, and
`%TEMP%\\ronin-vex-6012ed5-20261108-rerun`.

This closes local technical evidence for the runtime candidate, but not release:
the 13-family ledger remains 0/13, the VEX exception needs security-reviewer
sign-off, Trivy is unavailable on this host so container SBOM inventory is not
closed, and maintainer/legal/product, provider, rollback and manual visual
decisions remain open. The decision is therefore still **NO-GO**.

## 4 November clean-source diagnostic refresh

The broad checks below were rerun on clean implementation SHA
`b97255683f56c0643df64928941b79721d492dc7`: Python full suite **4,510 passed,
77 skipped, 0 failed**; PostgreSQL + coverage suite **4,558 passed, 27 skipped,
0 failed** and all configured coverage floors passed; performance **5/5**;
Docker integration **27/27** plus strict acceptance **15/15**; live browser/API
**33/33** across 25 routes and 213 real requests/log correlations; static
Playwright **112/112**. Ruff, format, mypy, architecture, negative gates,
OpenAPI, 196-route consistency, web audit/budget, dependency surfaces,
skills and cross-language protocol checks passed. Receipts are indexed in §58
of `PUBLIC_V1_BUILD_PLAN.md`.

The build checks then exposed a cwd collision in the PyRonin artifact gate. It
was fixed in implementation commit `bf9d0f7`; the focused regression passed
19/19, and the repaired gate built/installed PyRonin wheel+sdist `0.0.1a0` and
passed 90/90 installed SDK tests. This fix changes the source after `b972556`,
so its full-suite/Docker/live/UI results do not qualify `bf9d0f7`. The PyRonin
receipt does not qualify Ronin's main wheel/sdist, still versioned `0.0.0`.
Candidate-wide checks must be repeated after implementation is frozen.

## Product scope guardrails

- No integrated GenAI, RAG, model invocation, or in-product agent runtime in
  any Ronin tier. Coding-agent skills remain external portable instructions.
- No Public v1 multi-user identity or administration. Those capabilities are
  Ronin Pro scope and are excluded from the public claims and acceptance set.
- No CI. Release evidence is produced by the documented manual local gates.
- Public v1 denominator is P1–P8 and P10–P14: 13 families.
- A smaller MVP is a separate product decision with separate claims, profile,
  acceptance journeys, evidence bundle and decision; it is not an automatic
  way to turn a failed Public v1 into GO.

## Maintainer product decision — must be signed before candidate freeze

Choose exactly one release path. The present recommendation is **delay**;
Public v1 vs. Local MVP and the public version remain unapproved.

| Choice | Scope and consequence | Evidence threshold |
| --- | --- | --- |
| Ronin Public v1 | Keep the full local platform claim and all 13 active families. | All 13 family rows, all ten `release_required` gates, 15/15 strict v0.1 Docker acceptance, full manual UI review, clean-candidate evidence. |
| Ronin Local MVP | Publish a separately named and scoped product; explicitly hide/defer excluded capabilities and use its own `local_mvp_required` profile. | 7/7 MVP journeys, at least 14 live cases over 12 routes, all ten MVP gates, clean-candidate evidence, approved MVP claims and manual UI review. |
| Delay | Do not publish while any mandatory acceptance, human decision or candidate-bound gate remains open. | Keep the current NO-GO record; resume only with a new dated decision checkpoint and candidate plan. |

| Decision field | Maintainer record |
| --- | --- |
| Selected path | **PENDING SIGN-OFF** |
| Public product/version string | **PENDING MAINTAINER DECISION** (package metadata currently says `0.0.0`; this is not an approved release version) |
| Tag and artifact naming policy | **PENDING MAINTAINER DECISION** |
| Supported-platform matrix revision | **PENDING MAINTAINER DECISION** |
| Claims ledger path + SHA-256 after approval | **PENDING MAINTAINER REVIEW** — current claims file is a draft |
| Decision maker, date and signature/record link | **PENDING** |

Do not start the final candidate freeze until this record is complete. Choosing
an option does not waive its gates; choosing delay is a valid release outcome,
not a failed test result.

## Mandatory release gates

Every row must identify the same candidate commit and, where relevant, the
same image/package digests. “Implemented”, a historical pass, or a filtered
diagnostic does not close a gate.

**Historical gate table — runtime `8a85586`, VEX `61d9135d` (superseded; retained for traceability):** the
candidate-bound technical receipt below supersedes stale historical numbers in
the long gate cells: installed artifact qualification is `90/90`; Docker is
`27/27` with strict `15/15` on image
`sha256:cdf1957805932cf9742c3c23cc739bc6476f2388b8e88e160fc7c5c5276f705c`;
live is `33/33` with `248` correlated events; static Chromium is `130/130`;
Python/PostgreSQL is `4562/4589` with 27 explicit skips and 0 failures; coverage
passes `53/53` and `62/62`; Gitleaks and pip-audit are clean; SDK SBOM/provenance
verify; VEX is `3 raw / 0 applied`; container SBOM, human VEX/security, manual
visual, family/provider, legal, rollback and release-governance gates remain
open.

| Gate | Evidence required to mark PASS | Current decision state | Closure owner |
| --- | --- | --- | --- |
| Candidate identity | Clean worktree, exact commit SHA, branch/tag policy recorded, immutable wheel/sdist/image digests. | **OPEN** — clean exact-SHA checkout exists at runtime `8a855866` with documentation receipt `b0ea2cf6`, wheel/sdist identity and image `sha256:cdf1957805932cf9742c3c23cc739bc6476f2388b8e88e160fc7c5c5276f705c`; final branch/tag policy, artifact bundle and release freeze are not approved. | Release operator |
| Local quality | Full `make check`, complete Python/PostgreSQL suite, coverage thresholds, performance budgets, typing, formatting, architecture and status consistency; no unexplained skips/failures. | **OPEN** — historical dirty-worktree suite passed 4,467 with 26 skipped and 0 failed. The newer full rerun selected 4,558 and reconciled JUnit/timings exactly (4,531 passed, 26 skipped, 1 architecture failure); the undeclared existing `studio_server → studio_semantic` edge is now declared and the affected architecture/summary tests pass 25/25, but a full post-fix rerun is still required. Branch coverage and every Makefile coverage threshold passed (including storage per-file 53 files). The old v3 timing JSON omitted two module-level collection skips; reporter v4 now records them separately, and its focused contract test reconciles totals with JUnit. Mypy 437 source files; Ruff format/lint 899 files; OpenAPI snapshot; architecture and negative gates; 187 route operations; Studio surface 125/229; web audit 60 files with zero failures; web budget; canonical JSON/protocol; dependency surfaces; capability ledger; skills validate; performance 5/5. Full-suite evidence `%TEMP%\ronin-python-full-current-20261103`; static gate logs `%TEMP%\ronin-static-quality-current-20261103`; coverage logs `%TEMP%\ronin-coverage-gates-current-20261103`. On 2026-11-04, the full Python diagnostic on dirty source `7b6c018` passed 4,487, skipped 76, failed 0; the coverage-configured suite passed 4,482, skipped 76, failed 0. All Makefile coverage floors passed, including the storage per-file gate (53 files); the separate performance suite passed 5/5. These runs predate clean HEAD `87f4e5b`; full `make check`, exact-candidate qualification and PostgreSQL/Docker remain **OPEN**. The optional SDP JSON-stdio provider adapter is not configured; its real subprocess protocol test passes locally, and the installed official CLI does not advertise a JSON-stdio compile command. Per Data Engineering docs this adapter is optional and does not replace or block the official CLI gate. SDP official CLI passed 1/1 and Spark Connect passed 1/1 against real Spark 4.2.0 in dirty diagnostic receipt `%TEMP%\ronin-spark-connect-qualification-20261103-ccbb305d`, and the full candidate-bound `make check` receipt does not exist. The 8 POSIX-specific Windows skips passed separately on Linux (8/8, read-only repo mount, receipt `%TEMP%\\ronin-posix-qualification-20261103-0841ce5d`); Trino 2/2 and OTLP 1/1 also passed against real local services. These are dirty-worktree diagnostics. | Engineering |
| Security | Secret scan, dependency audit and image scan receipts for exact final artifacts; findings triaged with no unaccepted critical/high items. | **OPEN / HUMAN REVIEW** — exact candidate Docker Scout 1.27.0 found 3 raw reviewed findings and 0 after digest-bound OpenVEX for image `sha256:cdf1957805932cf9742c3c23cc739bc6476f2388b8e88e160fc7c5c5276f705c`; VEX receipt `%TEMP%\ronin-vex-8a85586-20261108`. The exception still requires security-reviewer acceptance; Trivy is unavailable and container SBOM review remains open. | Security reviewer |
| Docker qualification | Current-checkout image by digest; complete real Docker/PostgreSQL/Floci/Azurite suite, 0 skips/failures, strict v0.1 acceptance 15/15, cleanup receipt. | **TECHNICAL PASS / RELEASE OPEN** — candidate `8a85586` passed `27/27`, 0 skips/failures, strict acceptance `15/15`; image `sha256:cdf1957805932cf9742c3c23cc739bc6476f2388b8e88e160fc7c5c5276f705c`; cleanup succeeded. Evidence: `%TEMP%\ronin-docker-8a85586-20261108`. | Engineering |
| Live browser/API | All supported routes and required mutations exercised against Ronin API and real backing services; selected cases, HTTP status/body, persisted state, visible OK/WARN/ERROR and correlated logs agree. | **TECHNICAL PASS / RELEASE OPEN** — clean candidate `8a85586` passed `33/33` Playwright cases across 25 routes (24 API-backed), using worker image `sha256:cdf1957805932cf9742c3c23cc739bc6476f2388b8e88e160fc7c5c5276f705c`; 248 real HTTP events (233 OK, 15 expected WARN), all correlated to structured logs; no 5xx/network errors or unexpected authorization gaps. Evidence: `%TEMP%\ronin-live-8a85586-rerun-20261108`. | Product QA |
| Accessibility and visual review | Manual review on supported viewports: navigation, responsive layout, keyboard/focus, contrast, brown visual system, tutorials and screenshots/issues resolved. | **OPEN** — candidate-bound static Chromium suite passed `130/130` with accessibility, keyboard/navigation, UI behavior and responsive checks; manual visual/product sign-off is still unrecorded. | Product QA |
| Installed artifacts | Build wheel and sdist from candidate; install in clean environments; smoke supported commands, assets, routes and upgrade path; save exact outputs and digests. | **TECHNICAL PASS / RELEASE OPEN** — clean artifact qualification passed `90/90`; wheel `07b3663fc2404bce918efff40a3aece66ac823778338a5b8ce044e93fe6cd5bd`, sdist `9ef193d18e60dac70e64f62b472ab62b64628224bdf427eba4d28db6599811e3`; metadata remains prerelease/no approved public version. Evidence: `%TEMP%\ronin-artifact-qualification-8a85586.json`. | Release operator |
| SBOM and provenance | Generate CycloneDX and provenance from exact final wheel/sdist/image; validate subject digests and source identity. | **TECHNICAL PASS / RELEASE OPEN** — current artifact identity, CycloneDX and local provenance verified for runtime `8a85586`; container SBOM inventory remains open because Trivy is unavailable. Evidence: `%TEMP%\ronin-supply-chain-8a85586.json`. | Release operator |
| License and NOTICE | Resolve every human review decision, validate dependency inventories for supported OS/Python profiles, approve NOTICE and redistributed assets. | **OPEN / HUMAN DECISION** — do not infer legal approval from inventory generation. | Maintainer/legal reviewer |
| Artifact identity | Manifests and release receipts bind every published filename, digest, source SHA, profile, complete execution scope and gate result; aggregate verifier rehashes every file and returns `passed`. | **OPEN** — no complete same-candidate ten-gate bundle; the scope and unconditional rehash changes are unexecuted. | Release operator |
| Capability journeys | Integrated end-to-end journeys and provider/security evidence for each Public v1 family P1–P8 and P10–P14. | **OPEN: 0/13** — every family remains unqualified as a release family. | Feature owners + Product QA |
| Platform and support claims | Explicit supported OS, Python, Docker/Compose and local Kubernetes matrix; every claim has matching installed/runtime evidence. | **OPEN** — matrix incomplete. | Maintainer |
| Docs and recovery | Clean installation, configuration/secrets, upgrade, rollback, local DB+artifact restore and external object-store recovery instructions reviewed against tested behavior. | **OPEN** — dirty-tree diagnostics exist for Compose DB+local-data restore, Helm/kind install/restart and Floci/Terraform lifecycle. Repeat the relevant paths on one clean candidate; upgrade/rollback rehearsal and external object-store recovery remain. | Documentation + Operations |

## Historical candidate-bound technical receipt — runtime `8a85586`

The current receipt for the runtime candidate is:

- Web: Chromium `130/130`; web audit `63` files with zero failures; budget
  `2,051,458` asset bytes, `62` requests, `35` modules, `8` stylesheets and
  `4,992` HTML bytes. Data Engineering's decision workbench is covered by the
  focused and full suite.
- Installed artifacts: `90/90`; wheel digest
  `07b3663fc2404bce918efff40a3aece66ac823778338a5b8ce044e93fe6cd5bd`; sdist
  digest `9ef193d18e60dac70e64f62b472ab62b64628224bdf427eba4d28db6599811e3`.
- Docker: `27/27`, strict v0.1 `15/15`, zero skips/failures, image
  `sha256:cdf1957805932cf9742c3c23cc739bc6476f2388b8e88e160fc7c5c5276f705c`;
  `%TEMP%\\ronin-docker-8a85586-20261108`.
- Helm/kind: isolated lint, Secret boundary, install/readiness, health/API,
  persistence, restart and cleanup passed; `%TEMP%\\ronin-helm-8a85586-20261108`.
- Live: `33/33`, `25` active routes, `24` API-backed, `248` correlated events
  (`233` OK, `15` expected WARN), zero server/network errors and zero unexpected
  authorization gaps; `%TEMP%\\ronin-live-8a85586-rerun-20261108`.
- Security and supply chain: Gitleaks tree/history and pip-audit
  test/runtime/bootstrap are clean; SDK SBOM/provenance verify; VEX has `3`
  raw and `0` applied findings for the exact image; container SBOM remains
  open because Trivy is unavailable.
- Python/PostgreSQL: `4562 passed`, `27 skipped`, `0 failed` of `4589` in
  `%TEMP%\\ronin-python-full-8a85586-20261108`; coverage passes `53/53` and
  `62/62`; both public status-ledger contracts pass. The skips are explicit
  environment/provider/POSIX gates.

This is a technical candidate receipt, not a release GO. The family ledger is
still `0/13`, security/VEX acceptance, manual visual review, legal/NOTICE,
provider/support matrix, rollback, governance and container SBOM gates remain
open.

## Historical candidate-bound technical receipt — runtime `6012ed52`

The stale historical wording in the gate table above is retained for audit
history; the current candidate-bound technical result is:

- Python/PostgreSQL: `4562 passed`, `27 skipped`, `0 failed` of `4589` in
  `%TEMP%\\ronin-python-full-6012ed5-20261108`.
- Installed artifact: isolated PyRonin wheel/sdist qualification `90/90`;
  identity manifest binds commit `6012ed52` and the exact wheel/sdist digests.
- Docker: `27/27`, strict v0.1 `15/15`, zero skips/failures, image
  `sha256:89b122401876ff1b82f06b9e1f20dab3fa077981fb9bf51e264d3bd00d5b6be0`,
  cleanup passed; `%TEMP%\\ronin-docker-6012ed5-20261108`.
- Helm/kind: lint, Secret boundary, isolated cluster, install/readiness,
  health/API, persistence across restart and cleanup passed;
  `%TEMP%\\ronin-helm-6012ed5-20261108`.
- Live: `33/33` Playwright, 25 active routes, 24 API-backed, 247 correlated
  events, zero server/network errors and zero unexpected authorization gaps;
  `%TEMP%\\ronin-live-6012ed5-20261108`.
- Static UI: Chromium `128/128` on the final checkout; automated accessibility,
  keyboard, route traversal and responsive checks passed. Manual visual and
  accessibility sign-off is still open.
- Security/supply-chain: Gitleaks tree/history and pip-audit test/runtime/
  bootstrap are clean; SDK SBOM and provenance verify; container SBOM remains
  open because Trivy is unavailable.
- VEX: Docker Scout `3` raw findings and `0` after exact digest-bound OpenVEX;
  `%TEMP%\\ronin-vex-6012ed5-20261108-rerun`. Security-reviewer acceptance is
  still open; the VEX update is published in `9b1d16ef`.

This is a **technical pass**, not a release GO. The family ledger remains
`0/13`; provider credentials/matrix, legal/NOTICE/claims, manual review,
artifact/SBOM/provenance, rollback, support matrix and release governance still
prevent promotion.

## Family ledger

No family receives partial release credit. Each needs a complete supported
journey, its declared provider matrix, negative/failure behavior where
specified, and evidence from the same candidate. The phase numbers point to
the work plan's detailed phase table. In addition to the family-specific
evidence below, every family inherits the cross-cutting gates: candidate
identity, local quality, security, status consistency, Docker qualification
where applicable, live browser/API, accessibility, installed artifacts,
SBOM/provenance, license/NOTICE, and artifact identity. A family-specific test
cannot replace any of those gates.

| Family | Plan phase(s) | Minimum integrated proof for this family | State |
| --- | --- | --- | --- |
| P1 Workspace, projects, source control | 4, 11, 12 | UI/API/SDK operator journey; project export/import; secret-safe manifests; revision identity; audit. | **OPEN** |
| P2 Connections and ingestion | 5, 12 | Supported provider/format matrix; preview, sync, incremental replay, failure/retry/recovery and persisted UI/API state. | **OPEN** |
| P3 Lakehouse and SQL | 5 | Declared table formats, bounded SQL/bindings/pagination, persisted query result and provider error paths. | **OPEN** — the local-composed SQL and Semantic Studios now share a project-isolated DuckDB engine with refreshable Parquet relations under `RONIN_SQL_PARQUET_ROOT`; 59/59 focused DuckDB, local-composed SQL, semantic runtime/OpenAPI and HTTP tests passed, including root loading, same-name tenant isolation, replacement/removal and the authenticated dashboard API. The semantic live journey executes SQL from a real Parquet fixture and renders the five-row result (receipt `%TEMP%\ronin-live-semantic-dashboard-retry-20261103`). Also, two real-service Trino 484 tests pass (parameter binding and byte-budget boundaries) using image digest `sha256:2704eb53935af5e582d63d6033e9bf99d20c325e9b0e30b1016ef59a4773979f`; receipt `%TEMP%\ronin-trino-qualification-20261103-e7a48077`. These dirty-worktree diagnostics do not close the complete integrated P3 journey or candidate-bound provider matrix. |
| P4 Data Engineering Studio | 6, 12 | Author/edit/run/publish through product surface; real worker, source revision, output/lineage and evidence. | **OPEN** |
| P5 Durable DAG scheduler | 6, 10 | Trigger and ordering; retry/backfill/cancel; crash/restart recovery using supported persistence. | **OPEN** |
| P6 Catalog, lineage, ontology and graph | 7 | Persisted inventory plus integrated query/import/replay/conflict rollback. | **OPEN** |
| P7 Quality and contracts | 8, 9 | Built-in/custom checks, sandbox limits, severity transitions and evidence linked to assets/runs. | **OPEN** |
| P8 Classic ML | 8 | Reproducible dataset/train/evaluate/register/infer/drift and artifact lifecycle; no GenAI runtime. | **OPEN** |
| P10 Semantic models and dashboards | 9, 12 | Model/metric/filter/dashboard lifecycle, workspace-isolated API/Bundle roundtrip, legacy-scope migration and dashboard fan-out/cancellation budgets. | **OPEN** — project storage keys bind workspace and project, and identical project IDs remain isolated in real HTTP/SQLite tests. The current dirty-worktree live UI journey lists a model, exports/reviews/imports its Bundle and executes the dashboard against five real Parquet rows: 1/1 browser case, 7/7 API calls HTTP 200, all correlated to structured logs, 0 warning/error/network events in 34.73 s; receipt `%TEMP%\ronin-live-semantic-dashboard-retry-20261103`. PostgreSQL/Kafka were not started and route-wide audit was not run. Both SQL runtimes preflight up to 12 tiles and 100,000 aggregate requested rows, then enforce 15 s total SQL time and an 8 MiB response cap; combined runtime/OpenAPI/workspace HTTP regression passed 88/88, including 13 tiles rejected pre-query. Existing unscoped SQLite rows still need operator-selected workspace migration via `tools/migrate_semantic_project_scope.py`; PostgreSQL import and complete candidate-bound family journey remain open. |
| P11 Streaming | 9, 10 | Ingest, offsets/checkpoint, backpressure, replay/sink, lag and failure recovery against local broker. | **OPEN** — dirty-worktree Redpanda+Ronin browser/API diagnostics pass: Bundle export/plan/reset-import, consume, resume-import and lag preservation; bounded 2/2/1 batches, idle replay and poison-message 422 with checkpoint/lag unchanged; plus a real JSON record over 1 MiB rejected with sanitized 422 and unchanged lag, followed by explicit stream repoint/reset, successful recovery-topic consume and lag 0. Latest overload/recovery run passed 1/1 Chromium; all 36 API calls correlated to structured logs (32 OK, 4 expected WARN), zero server/network errors, PostgreSQL not started and cleanup succeeded (60.07 s total). Exact receipt: `%TEMP%\\ronin-live-streaming-overload-final-7b49698233e9452c8954a8c5b1cc1ed8`. Focused Python/API/architecture/OpenAPI and Chromium Bundle selections passed earlier; full P11 family qualification still needs broader operational evidence and a clean candidate. |
| P12 Observability, alerts and FinOps | 9, 12 | Real state transitions, redacted structured logs, metrics, alert delivery and budget/usage evidence. | **OPEN** — one real OTLP/HTTP Collector integration passed traces, metrics and logs (image digest `sha256:45392d534c1edcc809c2d112394029246bc679d2ae5ea7081414a1fc74f2c621`; 1/1, no skips/failures, cleanup succeeded; diagnostic receipt `%TEMP%\ronin-otlp-qualification-20261103-f933985d`). Alerts, FinOps journeys and same-candidate qualification remain open. |
| P13 Security and governance | 4, 10, 13 | Single-operator auth, scope/secrets/audit and negative authorization tests; no multi-user claim. | **OPEN** |
| P14 Deployment and operations | 3, 10, 13 | Prior dirty-tree diagnostics: Compose restored PostgreSQL plus local artifact/evidence files; Helm/kind exercised health, jobs API and queued-job persistence after pod restart; Floci qualification used Terraform 1.13.5 + AWS provider 6.65.0 and verified destroyed resources/state empty. Repeat candidate-bound Compose/Docker/Helm/Floci evidence, rehearse upgrade and rollback, state external object-store backup/recovery limits. The host's 1.16.2 Terraform executable does not satisfy the qualification pin; the archived 1.13.5 run proves that the required toolchain was used previously, but not for the current candidate. Do not relax the pin. See plan §§10 and 42–45. | **OPEN** |

## Evidence ledger rules

For every suite receipt, record these fields before changing any row to PASS:

| Field | Required value |
| --- | --- |
| Candidate | Exact commit SHA, clean worktree declaration, branch/tag identity. |
| Artifacts | Wheel, sdist, runtime/probe image digests and manifest paths, as applicable. |
| Invocation | Exact command, tool versions, selected node IDs, deselected count and filter. |
| Result | Passed/failed/skipped/xfail/error totals; skip reasons; elapsed wall time and test time. |
| Scope | Receipt declares `execution_scope=complete`; filtered, selected, partial or exploratory runs declare `diagnostic` and cannot close a required gate. |
| Runtime proof | Service/provider versions, HTTP request/response evidence, persisted-state assertion, visible UI state and correlated logs for live journeys. |
| Receipt | Absolute evidence directory with JUnit, logs, screenshots/review notes, scans and cleanup result. |
| Limitations | Excluded routes/providers/platforms, dirty-tree caveat, stale image caveat and the next required gate. |

The local qualification runners may be used for iteration with a dirty tree,
but label that output diagnostic. Before candidate qualification, first freeze
the code and create a clean source candidate; then rerun every affected gate
and the ten-gate release profile against that same candidate. A new source
change invalidates the affected candidate-bound receipts; do not carry an old
PASS forward by editing the evidence ledger.

## Decision procedure

1. Freeze scope and resolve package/product version, public claims, support
   matrix, license/NOTICE decisions and tag policy.
2. Finish implementation, then create one clean candidate. Record its SHA and
   immutable artifact digests before qualification.
3. Run the fast-to-full sequence in
   [`TESTING_FAST_TO_FULL.md`](../testing/TESTING_FAST_TO_FULL.md). Filtered
   tests are feedback only; they cannot close candidate-wide gates.
4. Run each mandatory family and release gate against that same SHA. Preserve
   JUnit, structured logs, API traffic, screenshots/manual checklist, scan
   reports, SBOM/provenance and cleanup receipts.
5. Reconcile the matrix and gate receipts. Resolve failures and repeat affected
   gates; any source change creates a new candidate and invalidates old
   candidate-bound evidence.
6. Mark **GO** only when all gate rows and all 13 family rows are PASS, there
   are no open P0/P1 issues or unaccepted critical/high findings, the ten-gate
   aggregate is `passed`, and the maintainer signs the exact artifact manifest.
7. Otherwise mark **NO-GO** and delay. If considering Local MVP, create and
   qualify its separate 7-journey/10-gate profile before changing the launch
   claim.

## Current decision

**NO-GO — delay the launch.** The planned 3 November 2026, 09:00 launch time
has passed. The current implementation baseline is clean, but no frozen release
candidate binds the evidence. Recent diagnostics cover the broad Python/
PostgreSQL suite, Docker/strict acceptance and live browser/API paths, but do
not qualify every family or artifact on one common candidate. The ledger remains
0/13; human license/NOTICE and version/claims decisions remain open, as do the
candidate-bound manual visual review and several family journeys. These
diagnostic passes cannot overturn those blockers.
