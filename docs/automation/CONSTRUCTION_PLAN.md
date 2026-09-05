# Ronin canonical construction plan

_Last synchronized: 2026-09-05. Reviewed repository baseline: `main` at `e275b3a41649975da13ef9af787111467cc664d3`; real Docker qualification, typed isolation qualification and async execution ports are already published. This Builder slice adds repository secret/dependency qualification and is not considered published until exact-head and post-merge evidence are green._

## Vision and principles

Ronin is a complete, professional, free, open-source, self-hostable and vendor-neutral Data + AI platform. The product must cover the whole lifecycle from ingestion and storage through engineering, SQL, streaming, governance, BI, ML, GenAI and agents, while feeling like one coherent product with shared identity, projects, assets, search, lineage, policy, costs, execution, observability, Git and administration.

Permanent principles: capability-first canonical domain; replaceable adapters/SPIs; local-first progressive enhancement; immutable/deterministic representations where practical; event/evidence-first execution; explicit failure over silent semantic loss; secure-by-default; portable/exportable artifacts; no mandatory proprietary control plane; no provider branches in canonical domain; Apache-2.0 and open-development habits compatible with a possible future ASF path without claiming ASF status.

## Architecture target and boundaries

Canonical domain packages own immutable product semantics and may not perform filesystem, network, process, environment or provider I/O. Side effects live behind adapters. Current executable dependency rules are enforced by `tools/architecture_gate.py`.

Target layers:

- `studio_core`: IDs, projects, Git intent, runtime capability requirements/resolution, operator and diagnostic contracts, canonical IR.
- `studio_notebook`: portable authored notebooks and explicit execution dependency graphs.
- `studio_kernel`: preparation, execution requests/results, reproducibility, session policy and execution evidence contracts.
- `studio_runners`: concrete local/container/runtime adapters; never the canonical domain.
- `studio_orchestrator`: Job -> Run -> Attempt, retries, leases, scheduling, reconciliation, quotas and dispatch.
- `studio_storage`: transactional metadata/evidence/artifact persistence, retention, backup/restore and shared-writer guarantees.
- `studio_server`: composition root and API boundary.
- `studio_cli` and SDKs: stable user-facing control-plane clients.
- Future domain/application packages for catalog/governance, semantic/BI, ML/GenAI/agents, FinOps and observability should consume shared core contracts rather than fork identity/evidence/cost semantics.

Architecture debt to remove before E2 public API stabilization: orchestrator must depend on execution ports/contracts rather than concrete runner implementations; privileged runtime execution should remain isolated from the web/control plane.

## Complete Data + AI capability map

Status vocabulary: IMPLEMENTED, PARTIAL, PLANNED, BLOCKED, DEBT.

| Capability | State | Current evidence / target |
|---|---|---|
| Product foundation, strict typing, architecture gates | IMPLEMENTED | E0 quality gates, pure-domain allowlist, negative-gate tests |
| Multi-project workspaces | PARTIAL | `Project`, `ProjectCollection`; workspace UX/storage/admin pending |
| Git multi-repository project configuration | PARTIAL | primary/supporting bindings, neutral adapters, `.ronin/project.json`; real Git adapter qualification pending |
| Runtime profiles/capability negotiation | PARTIAL | neutral catalog/resolver/snapshots; ambiguity-safe selection policy, versioned capability semantics and dispatch binding pending |
| Canonical graph/IR | PARTIAL | immutable deterministic IR/operators/diagnostics; cross-language canonical vectors and broader operator semantics pending |
| Data integration/ingestion/connectors | PLANNED | adapter/plugin model, batch/CDC/file/API connectors |
| Lakehouse/object storage/table formats | PLANNED | neutral storage/table SPI; Iceberg/Delta/Hudi candidates only via evidence/adapters |
| Data engineering/codegen | PLANNED | reuse mature `sdp-studio` graph/codegen/source-map/runtime work |
| Notebooks | PARTIAL | portable authored notebooks, DAG, kernel contracts; interactive UX/runtime journeys pending |
| SQL/warehouse/federation | PLANNED | neutral query/warehouse SPI, catalogs, pushdown/federation |
| Streaming/real-time | PLANNED | stream contracts, checkpoint/recovery, event-time semantics, observability |
| Data quality/observability | PARTIAL | diagnostic/evidence primitives; rule authoring, profiling, SLAs/SLOs and runtime integration pending |
| Catalog/governance/lineage/ontology | PLANNED | shared asset identity, metadata, policies, lineage graph, glossary/ontology/search |
| BI/semantic layer/metrics/reporting | PLANNED | semantic models, governed metrics, query acceleration, dashboards/reporting adapters |
| Data science | PLANNED | environments, experiments, notebooks, reproducibility, distributed compute |
| Feature engineering/store | PLANNED | offline/online feature definitions, lineage, freshness, point-in-time correctness |
| AutoML/HPO | PLANNED | replaceable optimization engines, evidence/cost tracking |
| MLOps/model registry/serving/monitoring | PLANNED | model artifacts, promotion, serving SPI, drift/quality/cost monitoring |
| AI/LLM gateway | PLANNED | provider-neutral routing/fallback, model catalog, quotas, token/latency/cost evidence |
| Prompt/evaluation suites | PLANNED | versioned prompts/datasets/judges, reproducible eval runs |
| RAG/knowledge/vector/hybrid search | PLANNED | neutral retrieval/index SPI linked to catalog/ontology/lineage |
| Agents/agentic workflows | PLANNED | canonical `AgentRuntime` SPI, durable event ledger, tools/permissions/approvals, replay, OTel, cost per step |
| Security/compliance | PARTIAL | qualified local-container isolation, redaction and repository security qualification; scoped grants, RBAC/ABAC, secrets, audit and tenant isolation pending |
| FinOps | PLANNED | resource/cost attribution for every workload, budgets/quotas/alerts/forecast/showback/chargeback |
| Observability/operations | PARTIAL | structured execution evidence and durable ledger baseline; OTel, SLOs, alerts, runbooks pending |
| API/SDK/CLI/plugin system | PARTIAL | alpha `pyronin`; stable server/state-machine/OpenAPI/CLI/plugins pending |
| Packaging/release/supply chain | PARTIAL | prerelease pipeline plus repository secret/dependency qualification; clean-room OCI provenance and exact dependency/license locking still require reconciliation |
| Local/Docker/Compose/Kubernetes/air-gap | PARTIAL | hardened local Docker executor with real-engine qualification; Compose/Kubernetes/air-gap lifecycle incomplete |
| Backup/restore/DR | PLANNED | metadata/artifact backup contracts, restore validation, RPO/RTO profiles |
| Performance/scalability | PLANNED | deterministic benchmarks, bounded DAG/ledger/evidence guards, distributed scheduling/storage |

## Milestones E0 -> E10

- **E0 Foundation**: repository hygiene, architecture/quality/security/release gates, community/license/governance baseline. Quality and repository security qualification are implemented; repository rulesets, exact dependency/license locking and community/security policy work remain.
- **E1 Canonical execution foundation**: project/Git/runtime/IR/notebook/kernel/evidence/local runner contracts. Real-engine isolation qualification and async-safe execution ports are complete. Exit now requires Job/Run/Attempt semantics, shared persistence direction, scoped grants/runtime binding and E2-ready public boundaries.
- **E2 Durable control plane**: orchestrator, storage, server API, authn/authz, leases/idempotency/retry/reconciliation, project/workspace persistence, audit, first end-to-end local journey.
- **E3 Data engineering platform**: ingestion, codegen, source maps, pipelines, scheduling, SQL, lakehouse, Git collaboration; reuse `sdp-studio` aggressively behind current boundaries.
- **E4 Streaming and data reliability**: streaming runtimes, checkpoints, data quality, data observability, SLAs/SLOs, incident evidence.
- **E5 Catalog, governance and semantic/BI**: asset catalog, lineage, glossary/ontology, policy, search, semantic layer, governed metrics and reporting.
- **E6 Data science and MLOps**: experiments, feature engineering, AutoML/HPO, registry, serving, monitoring, distributed training.
- **E7 GenAI/RAG**: AI gateway, prompt/version/evaluation systems, knowledge/retrieval/indexing, safety/policy hooks, complete cost/token accounting.
- **E8 Agents**: `AgentRuntime` SPI, tool schemas, scoped permissions, approvals, durable replay/resume, evaluation, multi-agent graphs and per-step evidence/cost.
- **E9 Enterprise operations**: HA, DR, multi-tenant isolation, compliance evidence, advanced FinOps, quotas/budgets, Kubernetes scale, air-gap qualification.
- **E10 Ecosystem and maturity**: stable APIs/SDKs, plugin ecosystem, compatibility matrix, reproducible releases, community governance, performance leadership backed by benchmarks.

Dependencies are directional: E0/E1 trust boundaries precede durable orchestration; durable identity/evidence/cost/lineage contracts precede broad feature proliferation; local correctness precedes distributed scale.

## Prioritized backlog

### P0

1. Keep `main` green after every publication; never weaken quality/security gates.
2. Define canonical Job -> Run -> Attempt state machine and idempotency/retry semantics before stabilizing public `/v1/jobs` (#49).
3. Reconcile clean-room release/provenance hardening from PR #39 onto current `main` only when exact-head CI/release qualification is green (#43).
4. Establish exact dependency locking and transitive license qualification coordinated with repository vulnerability auditing (#58).
5. Keep the construction plan synchronized on every autonomous execution; never select completed Docker/async work from stale text.

### P1

1. Shared durable storage semantics: transaction/lease/CAS or equivalent uniqueness for `(attempt_id, sequence)` and workload state.
2. Runtime capability negotiation: versioned/namespaced semantics, ambiguity-safe policy and dispatch-time binding (#50/#61; resolve the decision conflict before implementation).
3. Real runtime reproducibility collector and Git checkout qualification.
4. Extend mutation qualification to `studio_kernel`, `studio_runners`, then `studio_notebook` with evidence-based ratcheting (#47).
5. Replace free-form permissions with typed scoped grants plus policy/evidence provenance (#52).
6. First notebook -> kernel -> real runtime -> durable evidence -> restart/recovery end-to-end journey after lifecycle/storage prerequisites (#57).
7. Portable content-addressed evidence/artifact references before durable storage hardens arbitrary strings (#53).
8. Cross-language canonical identity encoding and duplicate-member rejection before additional language implementations (#56).
9. Root control-plane server skeleton and OpenAPI contract tests for `pyronin` after the lifecycle contract (#54).
10. Reuse `sdp-studio` codegen/source maps/runtimes/debug/Git/collaboration behind current interfaces.
11. Harden repository URI query/fragment secret handling (#55), immutable CI action pins (#46), security policy (#45), and Docker qualification base-image pinning (#60) as focused trust-boundary slices.

### P2

- Connector/plugin SDK, local object/table storage, SQL/query SPI, ingestion pipelines, lineage graph, OTel exporter, data quality engine, semantic metrics foundation, Compose/Kubernetes packaging.
- Deterministic performance guards, backup/restore tests, accessibility and UX foundations.
- After E2 durability, decide and qualify the first portable open-table data journey (#59); do not preselect a vendor/format without the documented adapter-focused decision.

### P3

- Advanced distributed scale, additional proprietary adapters, ecosystem marketplace/discovery, sophisticated optimization and recommendation systems after core contracts are stable.

## Vertical-slice construction strategy

Each slice must deliver one coherent user/system capability end-to-end: canonical contract -> adapter -> persistence/evidence -> API/SDK/UX surface when applicable -> tests -> operational docs. Prefer slices that strengthen several future domains through shared primitives (identity, policy, evidence, cost, lineage) instead of isolated demos.

Before writing new capability code, search `SauronShepherd/sdp-studio` and `SauronShepherd/ronin-old` for reusable implementations and tests. Reuse semantics and mature code where boundaries permit; do not inherit provider branches, mutable global state, weak typing or mixed control/data-plane architecture.

## Acceptance criteria and quality gates

A capability is not competitive merely because an API/class exists. It is accepted only when it is usable, testable, observable, maintainable and operable.

Required gates by risk: Ruff format/lint, strict mypy, executable architecture contracts and negative fixtures, mandatory 100% line/branch coverage for covered pure-domain areas, mutation evidence with non-decreasing thresholds, unit/property/golden/contract/integration/adversarial/security/E2E/performance tests as appropriate, clean artifact install smoke, secret/dependency scans, immutable provenance for releases, and exact-SHA GitHub Actions evidence before merge and after publication.

Repository security qualification is fail-closed: pull requests scan protected base history plus the complete mergeable/current tree with an immutable scanner image and execution-time synthetic negative evidence. Dependency vulnerability audits target Ronin-declared dependency surfaces, not arbitrary hosted-runner packages. Exact lock/license qualification remains a separate stronger requirement.

## Security and isolation

- No secrets in canonical authored state or durable evidence; redaction is defense in depth, not primary containment.
- Permissions evolve from free-form strings to typed versioned grants with resource scope and policy provenance.
- Runtime isolation claims distinguish declared/tested/qualified evidence. Production policy may require QUALIFIED; the local Docker adapter is now real-engine qualified.
- Web/control plane must not require Docker daemon/root access; privileged execution belongs in isolated runner/agent boundaries.
- Authentication, authorization, audit, tenant/project isolation, encryption, key/secret adapters, supply-chain verification and policy evaluation are first-class product surfaces.
- Repository URI credentials belong behind `auth_ref`; query/fragment hardening remains tracked by #55.

## Persistence, recovery and DR

Current JSONL event storage is a local, restart-safe, single-writer baseline only. E2 must add transactional workload state, leases/heartbeats/reconciliation, monotonic terminal-state rules, idempotency keys, artifact stores, retention and migration/versioning. Backup/restore must be tested, not documented only; later HA/DR profiles define RPO/RTO with evidence.

## Observability, evidence, lineage and explainability

Every relevant workload (pipeline, query, notebook, Spark job, stream, training, deployment, inference, LLM/RAG/agent/tool execution) must emit correlated structured logs, metrics, traces, execution evidence, lineage and diagnostics. OpenTelemetry is a transport/integration, not the canonical domain. Evidence should support replay/debugging, policy decisions, source mapping and explainability without leaking secrets.

## FinOps

Resource and cost evidence must be attributable by workspace/project/user/run/attempt/asset when reasonable. Local execution records resources even when no cloud invoice exists. Build budgets, quotas, thresholds, alerts, forecasting, showback/chargeback and recommendation evidence on top of truthful observed usage; never synthesize cost from configured ceilings alone.

## Packaging, release and supply chain

Produce reproducible wheels/containers/charts with exact-version/tag validation, clean-room install smoke, SBOM, provenance/attestation tied to immutable OCI subjects, pinned release dependencies/actions/base images and immutable semantic release tags. Keep `alpha`/edge aliases explicitly mutable only where intentional. Repository branch/tag protection is an external administrative prerequisite and must not be marked implemented until GitHub reports it active.

The repository secret/dependency qualification gate is independent from release reproducibility: it blocks secret leakage and known vulnerable declared dependencies, while #43/#58 own immutable build-backend/artifact provenance and exact locked dependency/license evidence respectively.

## Deployment matrix

- **Laptop/local**: no mandatory distributed services; filesystem/SQLite-like local adapters may be used outside pure domain when appropriate.
- **Docker/Compose**: reproducible single-host control plane + runner/storage profiles.
- **Kubernetes**: scalable stateless control plane, isolated runners, persistent stores, quotas/policies, HA/DR options.
- **Air-gap/private**: local image IDs/digests, offline package/model/artifact mirrors, exportable manifests/SBOMs and no mandatory SaaS callback.

## API, SDK, CLI and plugins

`pyronin` remains alpha until the server state machine and OpenAPI contract exist. Public APIs require pagination, bounded responses/errors, secure authenticated transport defaults and compatibility/versioning. Add async SDK only after server semantics are stable. CLI should be a thin outer shell over the same contracts. Plugins/adapters expose capabilities and versioned contracts, not vendor branches in core.

## Git multi-project

Each project owns one primary repository plus optional supporting repositories, neutral adapter IDs, default refs and sync policies. Next implementation steps: reject secret-bearing URL query/fragment components, real Git adapter, safe checkout/root validation including symlink escape, dirty patch artifact support, object/ref identity evidence, auth-reference resolution outside committed manifests, and provider adapters without domain coupling.

## Runtimes

Projects may select nominal profiles (including ecosystem-specific profiles) and/or neutral requirements for engine, language versions, GPU, formats, libraries, streaming, ML and isolation. Adapters normalize provider semantics. The current lexical fallback is not a long-term product policy: #50/#61 must establish versioned capability semantics and an explicit ambiguity-safe ranking/binding contract before heterogeneous provider growth.

## ML, GenAI and agents

ML must cover experiments, datasets/features, environments, HPO/AutoML, distributed training, registry, deployment and monitoring with lineage/cost/evidence. GenAI adds a provider-neutral gateway, model catalog/routing/fallback, prompt versioning, evaluation suites, token/latency/cost accounting, safety/policy hooks, RAG and knowledge integration. Agents use a canonical `AgentRuntime` SPI with durable event ledger, typed tools, permissions/approvals, replay/resume, evaluation, OTel/audit and multi-agent graphs; Apache Maka or any other framework is only an adapter candidate justified by evidence.

## BI and semantic layer

Build governed semantic models and metrics as first-class assets linked to lineage/catalog/policy. Query engines and dashboard/reporting tools are adapters. The semantic layer must support consistent metric definitions, access policy, caching/acceleration evidence, versioning and exportability.

## Catalog, governance and ontology

A shared asset graph must unify datasets, tables, files, pipelines, notebooks, queries, models, prompts, vector indexes, agents and reports. Governance includes ownership, classification, policy, glossary/ontology, lineage, search, audit and lifecycle/retention. Avoid separate catalog islands per workload type.

## Performance and scalability

Establish deterministic micro/contract benchmarks before optimization; add regression budgets for DAG analysis, canonicalization, ledger replay, storage, query planning and API paths. Scale via replaceable storage/queue/compute adapters after semantics are proven locally. Performance claims require benchmark methodology and reproducible evidence.

## OSS reuse and adapters

Primary reuse sources: `sdp-studio` for data engineering IR/graph/operator semantics, codegen/source maps, runtimes/debug, Git/collaboration, auth/scheduling, UI and deployment; `ronin-old` for selective native execution/Gluten/Velox, execution results, redaction, notebook/session/isolation concepts. Third-party OSS or proprietary services are selected by correctness, maturity, security, interop, portability, cost, licensing, community, maintainability and UX; no brand receives canonical status by default.

Repository-level security/release qualification does not justify copying product code from either historical project. For the current slice, the reusable evidence source is contributor PR #40's defensive intent and failing CI, reconciled on a Builder-owned current-main branch rather than modifying or merging the contributor PR.

## Risks, blockers and external/admin dependencies

- `main` currently lacks repository protection/rulesets (#31/#63); this needs GitHub administration and cannot be faked by CI.
- Release/provenance PR #39 and contributor security PR #40 are stale/independent branches; validated semantics must be reconciled on Builder-owned current-main branches rather than autonomously taking over contributor work.
- Dependency range solving remains non-reproducible until #58 lands even after vulnerability qualification is active.
- Broad platform scope risks fragmented UX; shared identity/evidence/policy/cost/lineage primitives are the countermeasure.
- Cross-language canonicalization must be defined before public content-addressed identities are expanded (#56).
- `PRODUCT_CONSTITUTION.md` and `CAPABILITY_MAP.md` remain absent and are explicitly tracked by #48; this security slice does not fabricate them as unrelated scope.

## Current evidence snapshot

- Starting/current reviewed `main`: `e275b3a41649975da13ef9af787111467cc664d3`, which completed real Docker qualification in PR #42.
- Async execution boundary is already published at `8f3b3e9af29884d535693e5594072b8db3124df2`; typed isolation qualification is already published at `29279ccad665bf6bf4528f046c48cb6d70394fd8`.
- Contributor PR #39 (`be6e78510fe64b2bf3dd5e8b3b3876a5fb87509c`) contains reusable release-hardening semantics but predates current `main` and remains contributor-owned.
- Contributor PR #40 (`78f79d7d43d69470b4431e568ca159c683615eef`) proved normal CI could be green while security qualification failed; its secret-like finding was traced to its synthetic scanner fixture rather than a confirmed credential, and its dependency audit mishandled the local Ronin package.
- Builder PR #64 implements the reconciled security gate. Product/security head `f9ebb48d8e49af33c8203d1dae7d3cd349ea1371` passed Security qualification run `33943552981` and CI run `33943552862` before canonical documentation synchronization; the final documentation head must pass the same authoritative workflow set before merge.
- The security gate exposed `pytest 8.4.2` as affected by `PYSEC-2026-1845`; the declared development range was advanced to patched `pytest>=9.0.3,<10` rather than adding an ignore.

## Next executable slice

**Reconcile prerelease artifact identity and OCI provenance (#43), then coordinate its exact build dependency policy with #58.**

Concrete scope for the next Builder execution:

1. Re-read current `main`, #43/#58, open contributor PR #39 and all new handoffs before selecting work.
2. Reuse PR #39's already-reviewed clean-room artifact and immutable OCI-subject concepts without modifying or merging the stale contributor branch.
3. Exact-pin or otherwise reproducibly lock PEP 517 build backends through the same policy that #58 will use for required dependency graphs.
4. Build once, smoke the exact wheel/sdist/image outside source-tree leakage, stage the exact image by immutable commit reference, capture the registry digest, and attest that immutable OCI subject.
5. Refuse semantic prerelease tag repoints while retaining only explicitly documented mutable aliases.
6. Keep release/security/quality gates independent and fail closed; do not mask dependency or provenance failures.
7. Run all exact-head workflows, update canonical records, merge only when green, then verify resulting `main` workflows.
