# Ronin Autonomous Builder operating rules

## Current validation mode

GitHub Actions CI and the exact-head qualification workflows are active for the current construction branch. They are evidence gates for the SHA that they actually execute; a green run does not imply that incomplete Public v1 capabilities, provider certification, legal review or repository administration are complete.

Current operating policy:

- wait for and inspect exact-head Actions runs after pushed changes;
- run relevant automated tests locally as part of implementation cycles;
- treat required CI/security/Docker/release evidence as a merge prerequisite when the workflow applies;
- validate changes by static code inspection, contract tracing, import/dependency review, schema/API consistency review, and targeted code-level reasoning only;
- preserve existing security, durability, performance, architecture, coverage, and acceptance requirements in the implementation even though they are not being executed as automated gates;
- never describe unexecuted tests or incomplete workflows as green;
- coverage thresholds and per-file baselines may only ratchet upward; lowering one requires a recorded human decision with justification;
- closing the corresponding issue is part of a slice's Definition of Done, alongside removing obsolete source branches;
- record material uncertainty explicitly when static inspection cannot prove runtime behavior.

Historical CI evidence remains background evidence for older SHAs; current claims must identify the exact candidate SHA and completed workflow run.

## Coverage and baseline ratchet

Coverage thresholds and per-file baselines are monotonic quality floors: they
may only increase. Lowering a threshold or baseline requires an explicit human
decision recorded in `docs/automation/DECISIONS.md`, including the measured
evidence and the reason the contract changed. A green build is never a reason
to lower a quality floor.

The current T4 floor is 60%. The latest full local qualification measured 69%
for the Public v1 domain packages (`1017 passed`, `12 skipped`); this margin is
an observed baseline, not permission to reduce the floor.

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

Use `docs/automation/SLICE_PRIORITY.md` together with the current canonical `BACKLOG.md` and `CONSTRUCTION_PLAN.md`. Qualification-only work must not be treated as product completion, but exact-head evidence is required for release claims.

The v0.1 dependency critical path outranks unrelated hardening. Do not expand into frozen E3-E10 scope while v0.1 contract gaps remain.

## Pre-merge code review

Before merging Builder work, reread current `main`, inspect the complete diff against that `main`, verify that no conflicting Builder PR owns the same domain, and perform static code-level checks appropriate to the slice. Merge only if the code review finds no known correctness, architecture, security, or contract blocker.

## Post-merge branch hygiene

Deleting the merged source branch is part of the Builder Definition of Done whenever that branch has no unmerged work remaining. If the active GitHub integration cannot delete refs, record the branch as an explicit repository-administration cleanup item rather than silently treating the merge as fully hygienic.

## Pre-PR benefit check

For a change presented as an optimization or throughput improvement, state whether the expected benefit materializes end to end or whether an adjacent unchanged line neutralizes it. Use code-path/complexity reasoning or already-available measurements; do not claim a measured performance win unless such evidence actually exists.
