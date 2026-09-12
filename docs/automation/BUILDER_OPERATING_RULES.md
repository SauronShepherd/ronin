# Ronin Autonomous Builder operating rules

## Current validation mode

GitHub Actions CI is intentionally disabled to avoid consuming GitHub Actions credits. The active workflow directory is empty; the previous workflow definitions are retained under `.github/workflows-disabled/` for possible future restoration.

Until the maintainer explicitly changes this policy:

- do not wait for, trigger, rerun, or require GitHub Actions;
- do not run automated tests as part of autonomous implementation cycles;
- do not make test execution or CI evidence a merge prerequisite;
- validate changes by static code inspection, contract tracing, import/dependency review, schema/API consistency review, and targeted code-level reasoning only;
- preserve existing security, durability, performance, architecture, coverage, and acceptance requirements in the implementation even though they are not being executed as automated gates;
- never describe unexecuted tests or disabled CI as green;
- record material uncertainty explicitly when static inspection cannot prove runtime behavior.

Historical CI evidence remains useful background evidence for already-published SHAs, but it is not required for new implementation work while this mode is active.

## Slice ownership

Builder work uses single-writer ownership per file domain rather than one global writer.

| Domain | Paths |
|---|---|
| `core` | `python/studio_core/**`, `python/studio_notebook/**` |
| `execution` | `python/studio_kernel/**`, `python/studio_runners/**` |
| `platform` | `python/studio_orchestrator/**`, `python/studio_storage/**`, `python/studio_vcs/**`, `python/studio_server/**`, `python/studio_cli/**` |
| `interface` | `packages/pyronin/**` |
| `infra` | `.github/**`, `docker/**`, `tools/**`, `Makefile`, `pyproject.toml`, dependency lockfiles |
| `docs` | `docs/**`, root Markdown policy/docs files, `examples/**` |

At most one open Builder PR may claim a domain. A slice touching multiple domains claims all of them. The PR body lists `Builder-Domains:` and is the claim. A later claimant must wait or rebase after the earlier claim merges; it may not overwrite or silently merge conflicting work.

## Slice selection priority

Use `docs/automation/SLICE_PRIORITY.md` together with the current canonical `BACKLOG.md` and `CONSTRUCTION_PLAN.md`. Under code-only validation mode, CI-evidence-only handoffs do not block implementation; keep them open/deferred until automated qualification is explicitly re-enabled.

The v0.1 dependency critical path outranks unrelated hardening. Do not expand into frozen E3-E10 scope while v0.1 contract gaps remain.

## Pre-merge code review

Before merging Builder work, reread current `main`, inspect the complete diff against that `main`, verify that no conflicting Builder PR owns the same domain, and perform static code-level checks appropriate to the slice. Merge only if the code review finds no known correctness, architecture, security, or contract blocker.

## Post-merge branch hygiene

Deleting the merged source branch is part of the Builder Definition of Done whenever that branch has no unmerged work remaining. If the active GitHub integration cannot delete refs, record the branch as an explicit repository-administration cleanup item rather than silently treating the merge as fully hygienic.

## Pre-PR benefit check

For a change presented as an optimization or throughput improvement, state whether the expected benefit materializes end to end or whether an adjacent unchanged line neutralizes it. Use code-path/complexity reasoning or already-available measurements; do not claim a measured performance win unless such evidence actually exists.
