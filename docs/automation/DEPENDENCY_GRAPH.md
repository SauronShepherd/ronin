# v0.1 dependency graph

_Current snapshot basis: `3e69c2a084260126f7eb87cbfbbe4bedcd77df2e` (2026-09-11), with the storage evidence-layer collapse represented by this change. Scope authority: `docs/product/V01_SCOPE.md`._

```text
#56 remaining canonical identity boundaries
  -> #22 residual architecture reconciliation

#58 exact resolved license evidence
  -> #95 artifact/license binding evidence
  -> #73 final release-process truth

#45 human private-reporting decision
  -> SECURITY.md/security navigation
  -> #70 security-sensitive template routing

#72 already-decided governance model
  -> #70 contributor surface
  -> #71 docs navigation

#50 runtime capability/ambiguity decision
  -> any future multi-runtime work
  -> #62 post-v0.1 neutral runner protocol

#57 qualification gate
  -> v0.1 release claim
  -> #59 post-v0.1 data-platform work

#63 repository/ref protection
  -> v0.1.0 tag publication
```

## Reconciled items

- **Storage evidence-layer collapse is code-complete in this change.** The exported concrete SQLite adapter is again `fenced_sqlite.SqliteJobStore`; the exported concrete in-memory adapter is `paged_store.InMemoryJobStore`. Schema-v3 evidence persistence and the shared max-100 Run bound live in those canonical paths, while `evidence_sqlite.py` and `evidence_memory.py` are compatibility re-exports only.
- **#99 is no longer an implementation dependency.** Immutable Job/Run/Attempt lifecycle types, lease/retry semantics and the storage-neutral `JobStore` Protocol already exist in `studio_orchestrator` and are consumed by current storage/worker code.
- **#95 implementation mechanics already exist** in `tools/artifact_qualification.py`; remaining work is exact candidate execution/publication evidence and binding to #58 license evidence.
- **#115 production implementation exists** for cgroup v1/v2 observed CPU/memory; remaining work is real-Docker/overhead evidence.
- **#62 is post-v0.1.** ADR-V01-009 establishes the language-neutral process-boundary direction before any remote/non-Python runner.
- **#57 is not current feature work.** Product code contains the historical step-01 and step-12 capabilities; strict 15/15 remains a future qualification gate.

## Current selection order

1. Finish #56 identity-bearing JSON call sites and complete boundary goldens.
2. Reconcile #22 residual architecture defects without reopening already-completed durable/auth/evidence work.
3. Complete the deterministic build-system/release-tool surface for #58; exact inventory/policy/NOTICE conclusions require real evidence and human review.
4. Publish the already-decided governance/contributor/docs/release surface (#72/#70/#71/#73), with #45 gated on a verified private reporting route.
5. Record the #50 runtime capability/ambiguity decision before any future multi-runtime expansion.
6. Revisit #57 and verification-only handoffs only if the maintainer explicitly restores automated verification.

Test/CI/measurement handoffs #47/#60/#69/#102/#163/#166/#167 remain preserved but are not implementation blockers while the repository is in maintainer-directed code-only mode.
