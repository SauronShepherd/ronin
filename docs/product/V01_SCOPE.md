# Ronin v0.1 scope

## 1. The sentence

Ronin v0.1 executes a notebook from a local Git project inside an isolated container, reproducibly, with durable per-cell evidence, and survives a worker restart by resuming where it left off.

## 2. In scope

1. Job → Run → Attempt persisted transactionally — owner: `studio_storage`.
2. Pure state machine, idempotency, retries, leases — owner: `studio_orchestrator`.
3. Worker with lease, heartbeat, crash reclamation — owner: `studio_orchestrator`.
4. Per-cell resume from the event ledger — owner: `studio_orchestrator`.
5. HTTP API `/v1/jobs` matching the published `pyronin` — owner: `studio_server`.
6. Static bearer token auth with typed scopes — owner: `studio_server`.
7. CLI: serve, worker, validate, plan, submit, status, logs, evidence, cancel, doctor — owner: `studio_cli`.
8. Local Git revision capture (commit + dirty digest) — owner: `studio_vcs`.
9. Container execution with per-cell log and resource evidence — owner: `studio_runners`.
10. Single image plus a working `docker compose up` — owner: `docker/`.
11. Reproducible quickstart under ten minutes from zero — owner: `docs/`.
12. All known defects from reviews #1 and #2 closed — owner: cross-cutting.

## 3. Explicit non-goals

- Do not add remote Git cloning, Git credentials, or repository synchronisation. v0.1 operates on a local checkout.
- Do not add Postgres, multi-node, HA, or multi-tenancy. v0.1 is single-node SQLite.
- Do not add any web UI.
- Do not implement E3–E10: ingestion, SQL, lakehouse, streaming, quality, catalog, lineage, BI, ML, GenAI, agents, or FinOps.
- Do not add Fabric, Databricks, Spark, or Kubernetes adapters. The only v0.1 runner is local Docker.
- Do not add `studio_codegen`, `studio_bridge`, `studio_native`, or `studio_debug`. They are removed from the gate matrix until they exist.
- Do not add OIDC, multi-user RBAC, or audit trails.
- Do not add level-parallel cell execution. v0.1 is sequential; existing `levels` metadata is reserved for v0.2.
- Do not publish the server to PyPI. v0.1 ships as an OCI image plus `pyronin` on PyPI.

## 4. The acceptance journey

1. Run `docker compose up -d`; the service becomes healthy in under 60 seconds.
2. Run `ronin doctor`; all checks pass.
3. Run `ronin validate examples/demo`; manifest, notebook, and DAG are valid.
4. Run `ronin plan examples/demo -t notebooks/etl`; execution order and levels are printed.
5. Run `ronin submit ... --idempotency-key k1`; receive job id J in `queued` state.
6. Let a worker claim the run and execute cells 1 through 3 of 6.
7. Kill the worker with `kill -9 <worker pid>`; its lease becomes orphaned.
8. Restart the worker and let the lease expire after 30 seconds.
9. Reclaim the run as attempt #2; resume at cell 4 and do not re-run cells 1 through 3.
10. Run `ronin status J`; observe `succeeded`.
11. Run `ronin logs J`; observe contiguous events across both attempts with a terminal event.
12. Run `ronin evidence J`; observe log and resource references for all six cells.
13. Submit again with `--idempotency-key k1`; receive J with no new job and no re-execution.
14. Run `ronin cancel J2` for a long job; observe `cancelled` and no leftover container in `docker ps`.
15. Use `Ronin(url).submit(...).wait()` from `pyronin`; observe the same outcome through the SDK.

## 5. Non-functional budget

| Metric | Budget |
|---|---:|
| p95 `POST /v1/jobs` | < 100 ms |
| p95 `GET /v1/jobs/{id}` | < 30 ms |
| Single event append (SQLite, `synchronous=FULL`) | < 5 ms |
| Crash reclamation | < 15 s after lease expiry |
| `docker compose up` to healthy | < 60 s |
| Server + worker RSS at idle | < 300 MB |
| Full `make check` | < 5 min |
