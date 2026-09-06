# Ronin Autonomous Builder operating rules

## Qualification is exact-head only

A Builder candidate is qualified only by workflow/check runs whose `head_sha` equals the exact pull-request head being considered for merge.

- Runs for superseded commits are informational and never block or satisfy qualification.
- A cancelled run for the exact head is re-dispatched once; the Builder does not wait on a superseded run.
- If the exact head has not reached a terminal qualification state within 45 minutes, re-dispatch once. If the re-dispatched exact-head qualification still cannot reach a trustworthy terminal state, stop the slice, leave the PR unmerged, and record the blocker.
- Never infer green from a different SHA, a branch-level aggregate, or a stale pull-request check.
- After merge, qualify the exact published `main` SHA again.

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

Use `docs/automation/SLICE_PRIORITY.md`. In particular, release-trust defects outrank feature throughput, but after trust is sound the v0.1 dependency critical path outranks unrelated same-priority hardening.

## Pre-PR benefit check

For a change presented as an optimization or throughput improvement, state in the PR description whether the expected benefit materializes end to end or whether an adjacent unchanged line neutralizes it. Cite a measurement or bounded complexity proof. Do not claim a performance win from a local primitive change whose caller still retains the original hot-path cost.
