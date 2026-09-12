# Changelog

All notable user-visible changes to Ronin are recorded here. Ronin is currently alpha; entries describe source-level implementation and compatibility changes and do not by themselves claim release qualification.

## Unreleased

### Breaking / compatibility tightening

- Public `POST /v1/jobs` request parsing now rejects duplicate JSON object members and non-finite numbers through the shared canonical JSON v1 decoder. Valid v1 canonical bytes and idempotency request digests remain unchanged.

### Features

- Durable local job/run/attempt execution with SQLite-backed state, worker leasing/reclaim, container execution, public evidence retrieval, typed project/action grants, authenticated HTTP control, CLI, OpenAPI, `pyronin`, production Compose topology, readiness, and observed container resource evidence are present in current source.
- Canonical JSON v1 now covers the public HTTP request/idempotency identity boundary in addition to existing internal identity-bearing surfaces.

### Fixes and hardening

- Storage evidence adapter layering was collapsed back to one canonical implementation per backend.
- Git dirty identity includes normalized untracked executable mode in production code.
- HTTP, storage, authorization, evidence, and canonical identity surfaces have received fail-closed hardening during v0.1 construction.

### Security-relevant changes

- Typed project/action grants and bearer authorization are implemented in the public HTTP surface.
- Secret-bearing and evidence/privacy boundaries are progressively hardened, but current automated Security qualification is disabled and no current-head security gate is claimed.

### Known limitations

- GitHub Actions and automated tests are currently disabled by maintainer policy; current `main` therefore lacks exact-head automated release qualification.
- The last authoritative automated frozen-journey result remains historical rather than current-head evidence; do not claim 15/15 until all fifteen steps execute on one exact candidate SHA.
- `SECURITY.md` is intentionally absent until a private vulnerability-reporting channel is selected and verified.
- Release license/NOTICE evidence still requires exact resolved-environment generation and human review.
- Repository/ref protection remains a release-gate requirement before `v0.1.0`, no later than 2026-11-01.
- Post-v0.1 breadth such as ingestion, CDC, lakehouse, SQL federation, streaming, catalog, BI, ML, GenAI, RAG, and additional runtimes remains out of scope.

## Compatibility policy

CLI, HTTP/OpenAPI, and `pyronin` are strict alpha surfaces. Incompatible changes must be coordinated across the affected components and called out here and in release notes. Identity-breaking changes require an explicit identity/schema version and migration rather than silent byte drift.
