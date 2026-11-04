# Changelog

All notable user-visible changes to Ronin are recorded here. Ronin is currently alpha; entries describe source-level implementation and compatibility changes and do not by themselves claim release qualification.

## Unreleased

### Documentation

- Reconciled the Public v1 implementation ledger, documentation index and
  README with the 2026-10-29 scope and test plan. Historical workflow results
  are separated from today's dirty-worktree diagnostics; current qualification
  remains blocked and no release candidate is claimed.
- Public claims now state that Ronin has no GenAI/RAG/in-product agent runtime;
  external coding-agent skills are kept separate. The public Helm chart is
  single-replica and has no multi-user configuration.

### Breaking / compatibility tightening

- Public `POST /v1/jobs` request parsing now rejects duplicate JSON object members and non-finite numbers through the shared canonical JSON v1 decoder. Valid v1 canonical bytes and idempotency request digests remain unchanged.
- Canonical JSON v1 now rejects integers outside `-(2**53 - 1)` through `2**53 - 1` so identity-bearing values remain exact for JavaScript and other IEEE-754 consumers. Larger values must be represented as strings; existing canonical vectors were checked and updated where necessary.

### Features

- Durable local job/run/attempt execution with SQLite-backed state, worker leasing/reclaim, container execution, public evidence retrieval, typed project/action grants, authenticated HTTP control, CLI, OpenAPI, `pyronin`, production Compose topology, readiness, and observed container resource evidence are present in current source.
- Canonical JSON v1 now covers the public HTTP request/idempotency identity boundary in addition to existing internal identity-bearing surfaces.
- The local-composed profile now manages the durable workflow scheduler lifecycle. Its local API covers cron schedules and fire history, event triggers and delivery history, immutable bounded backfill plans and cancellation, and workflow-run cancellation. SQLite and PostgreSQL scheduler persistence are exercised; this remains a single-operator local capability, not an HA/SLA claim.

### Fixes and hardening

- Storage evidence adapter layering was collapsed back to one canonical implementation per backend.
- Git dirty identity includes normalized untracked executable mode in production code.
- HTTP, storage, authorization, evidence, and canonical identity surfaces have received fail-closed hardening during v0.1 construction.

### Security-relevant changes

- Typed project/action grants and bearer authorization are implemented in the public HTTP surface.
- Secret-bearing and evidence/privacy boundaries are progressively hardened; local security qualification has not yet passed for the current candidate.
- Runtime and probe images now use digest-pinned Alpine bases, exact-version APK package locks, and a hash-locked, build-only pip 26.2.2 bootstrap; `apk upgrade`, pip, and its build tools are absent from the final images. Current image evidence is still dirty-worktree diagnostic, not release qualification.

### Known limitations

- CI workflows are excluded by maintainer policy; tests remain runnable manually. No exact clean-candidate release qualification is available for the current worktree.
- The last authoritative automated frozen-journey result remains historical rather than current-head evidence; do not claim 15/15 until all fifteen steps execute on one exact candidate SHA.
- `SECURITY.md` documents the private vulnerability-reporting route; repository configuration and release qualification remain maintainer-owned evidence.
- Release license/NOTICE evidence still requires exact resolved-environment generation and human review.
- Package version `0.0.0`, README alpha/v0.1 wording and Helm `0.1.0` still need a human-approved release identity.
- The supported OS/Python matrix, Helm/kind qualification and security scanners remain incomplete. The local Floci plan requires Terraform 1.13.5, while this host has 1.16.2.
- Ingestion, CDC, lakehouse, SQL federation, streaming, catalog, BI, ML and additional runtimes are not release-qualified until their stated journeys pass. GenAI/RAG/in-product agents are excluded from every Ronin tier, not deferred to a later Ronin release.

## Compatibility policy

CLI, HTTP/OpenAPI, and `pyronin` are strict alpha surfaces. Incompatible changes must be coordinated across the affected components and called out here and in release notes. Identity-breaking changes require an explicit identity/schema version and migration rather than silent byte drift.
