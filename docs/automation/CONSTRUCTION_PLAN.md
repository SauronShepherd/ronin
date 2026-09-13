# Ronin Public v1 construction plan

_Last synchronized: 2026-09-13 from main `b7e861f11a1399553fba0292f2b86760cc04d747` after PR #288. Scope authority: `docs/product/PUBLIC_V1_SCOPE.md`. Portability authority: `docs/product/PLATFORM_PORTABILITY_V1.md`._

Ronin Public v1 is **incomplete** until every mandatory capability family has an end-to-end supported path. This document is the active autonomous construction plan. The prior v0.1 plan is preserved verbatim at `docs/automation/history/V01_CONSTRUCTION_PLAN.md` and remains historical evidence only; its feature-freeze language does not override Public v1 scope.

## Validation mode

GitHub Actions and automated qualification remain disabled by maintainer policy. Source work may proceed through repository inspection, contract tracing, static review and code-level reasoning, but no new test/CI/release evidence may be claimed unless it is actually executed after authorization. Historical v0.1 evidence remains historical and must not be presented as exact-current-head qualification.

## Mandatory invariants

1. Canonical logical identity never derives from storage URLs, database surrogate keys, worker IDs, cloud/vendor IDs, credentials or other deployment-local locators.
2. Durable intent is persisted before authoritative side effects.
3. Stale workers/controllers are fenced wherever lease loss could otherwise permit an authoritative write.
4. Checkpoints advance only after governed output commit and required lineage/catalog persistence.
5. Scheduler logical retry remains separate from Job crash-replacement Attempts.
6. Portable state stores secret references only; secret material resolves at authorized execution/deployment boundaries.
7. Typed grants remain the authorization language; future OIDC identities map into those grants.
8. Artifacts/evidence remain storage-neutral and content-addressed.
9. Executable workload families integrate audit, observability and lineage.
10. Web Studio is an API client, not a second semantic implementation.
11. Migration reports classify every source object explicitly as exact, translated, partial, passthrough, unsupported or manual-decision.
12. No implementation presence is release evidence by itself.

## Current source position

Implemented foundations include durable Job/Run/Attempt execution; SQLite durability; leases, heartbeat, fencing, reclaim/resume and cancellation; content-addressed evidence/artifacts; canonical JSON/identity; workspace/project/environment foundations; typed grants; deployment-local secret resolution; deterministic Ronin Bundle archive IO; native project and connection semantic round-trips with explicit runtime/secret remapping; atomic project+connection multi-object commit; explicit selected catalog asset/revision/lineage subgraph export/planning and atomic commit; initial provider-neutral metadata ports; persistent catalog/lineage primitives; quality/ontology/audit/ML/GenAI domain persistence; local/Compose operation; and an advanced durable scheduler foundation.

Public-v1 capability state is maintained in `docs/product/PUBLIC_V1_IMPLEMENTATION_STATUS.md` and `docs/product/public-v1-status.json`. Those ledgers are implementation-status records, not release qualification.

## Active critical path

1. **Scheduler remaining work:** broad task adapters as target runtimes become executable; branching/skipped semantics if required; alert-backed durable notifications; public scheduler APIs/Studio; process/deployment wiring; PostgreSQL HA qualification after the PostgreSQL backend exists.
2. **Ronin Bundle semantic portability:** inspect workflow/pipeline snapshot and persistence contracts next; if they preserve canonical portable intent independently of deployment/controller state, extend the same verified inventory/planning/atomic-commit model there. Otherwise select the next metadata family whose contracts can round-trip honestly. Certification waits for real exact-head qualification evidence.
3. **Persistence boundaries:** finish provider-neutral store ports for scheduler, quality, ontology, audit, ML, GenAI, semantic, streaming, alerts/FinOps and identity.
4. **Open data plane:** Apache Arrow/Parquet, reference open table lifecycle (Iceberg), documented Delta interoperability and provider-neutral SQL engine with a lightweight reference adapter.
5. **Connector matrix:** PostgreSQL, JDBC, S3-compatible, Azure-compatible and HTTP/REST plus restart-safe incremental checkpointing.
6. **Quality/catalog integration:** execute contracts; add search, glossary, ownership, classification and OpenLineage interoperability.
7. **Public APIs + Web Studio:** expose supported workspace/data/scheduler/catalog surfaces and begin the generated-client Studio.
8. **Data Engineering Studio:** notebook, SQL and pipeline CRUD/versioning plus scheduler-backed authoring/execution journeys.
9. **Ontology/KG + graph:** interfaces, object instances, governed actions, freeze RQL v1 grammar/AST and implement a native reference graph executor.
10. **Semantic analytics:** semantic model compiler, reusable metrics and portable dashboards.
11. **ML/MLOps:** features, training, tracking, MLflow interoperability, evaluation, batch inference and serving.
12. **GenAI:** provider execution, embeddings/vector indexes, retrieval/RAG, evaluation, bounded agents/tools and cost/token tracing.
13. **Streaming:** restart-safe sources/processors/windows/sinks/checkpoints, connected to the existing scheduler event inbox.
14. **Operations:** OpenTelemetry-compatible telemetry, durable alerts/notifications and factual FinOps attribution/budgets/policies.
15. **Multi-user security:** OIDC users/groups/service identities mapped into typed grants, classification-aware governance and complete audit instrumentation.
16. **Server deployment:** PostgreSQL adapters, S3-compatible artifacts, server Compose profile, Kubernetes/Helm, scheduler HA and backup/restore.
17. **Migration profiles:** Fabric, Databricks, Dataiku DSS and Palantir Foundry/AIP only against executable Ronin target capabilities; every fixture must import, execute its supported subset and Bundle-round-trip.
18. **Release qualification:** only after maintainer authorization, run exact-candidate journeys/security/license/SBOM/provenance and configure branch/release protection.

## Scheduler semantics already landed

- cancellation (#265), timeouts (#267), snapshot-safe backfill (#268), shared pools (#270), leader fencing (#271/#273), daemon orchestration (#274/#275), and group backfill cancellation (#276) form the durable scheduler foundation.
- These do not complete P5; broad adapters, branching/notifications, public surfaces, deployment wiring and PostgreSQL HA qualification remain.

## Ronin Bundle semantics already landed

- **Archive integrity:** deterministic canonical manifest/archive IO, safe paths, bounded reads and full payload digest verification.
- **Project path (#278–#280):** semantic inventory/export, fully verified planning, explicit runtime remapping, provider-neutral atomic project/environment-binding commit.
- **Connection path (#282):** semantic inventory/export/import using portable metadata and `secret://` references, exact secret remaps and conflict-safe create/noop semantics.
- **Project+connection multi-object path (#283/#285):** deterministic topological staging, aggregate binding resolution, provider-neutral commit port and one SQLite transaction across resolved connections/projects/environment bindings.
- **Catalog path (#287/#288):** caller-selected revision subgraph export containing exact assets/revisions and lineage only when both endpoints are selected; verified dependency-aware planning; provider-neutral atomic commit; one SQLite transaction across assets/revisions/lineage with full rollback on late conflicts.

These cover only currently implemented metadata families. Catalog export remains explicit rather than whole-catalog because the provider-neutral catalog port lacks complete revision discovery. Workflow/quality/ontology/ML/GenAI and later data/semantic objects remain outside the native Bundle path. PostgreSQL has not implemented the Bundle commit ports. No certification evidence is claimed while automated qualification remains disabled.

## Blocked and human-decision work

- #199 and dependent automated qualification/release evidence: blocked until maintainer authorization.
- #45 vulnerability reporting route: human/security decision; do not invent a contact channel.
- #50 runtime capability namespace/value/ambiguity semantics: architecture decision before broad multi-runtime dispatch.
- #62 language-neutral runner protocol: architecture decision before supported non-Python/remote agents.
- License/NOTICE/attribution conclusions and release approval: human/legal review.
- #63 branch/ref protection: repository administration after meaningful required checks exist.
- Vendor credentials: user/environment supplied only; never fabricate or commit them.

## Public v1 release rule

A capability is not complete because a dataclass, store, UI mock or importer inventory exists. Executable capabilities require a real reference runtime; public capabilities require documented API/CLI/SDK/Studio paths as applicable; migrations require exhaustive object classification plus executable translated fixtures; release evidence must come from the exact candidate. If any mandatory family or reference journey lacks an end-to-end supported path, Ronin Public v1 remains incomplete.
