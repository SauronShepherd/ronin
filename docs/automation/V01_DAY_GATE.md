# v0.1 day gate — 2026-09-05

This checklist turns the Saturday planning pass into an auditable release-preparation gate. A box is checked only after its artifact is published on `main` and its applicable executable evidence is green.

- [x] Phase 1 — baseline capture and fresh-environment measurements recorded.
- [x] Phase 2 — v0.1 scope, non-goals, acceptance journey and budgets frozen.
- [x] Phase 3 — five v0.1 ADRs accepted with explicit week unblocks.
- [x] Phase 4 — eight-week construction plan and frozen E3–E10 backlog recorded.
- [x] Phase 5 — five missing v0.1 package skeletons and import smoke tests added.
- [x] Phase 6 — nine-package architecture matrix and negative cases executable.
- [x] Phase 7 — hash-locked dependency install, tiered coverage gates, Python 3.11/3.12 matrix, repository-wide quality perimeter, and nightly/manual mutation policy green.
- [x] Phase 8 — demo manifest/notebook committed and byte-for-byte regenerable.
- [x] Phase 9 — all fifteen acceptance-step placeholders exist; twelve Week-1 issues #75–#86 are attached to milestone `v0.1.0` due 2026-11-01.
- [x] Phase 10 — PR #74 is merged and published as `0dbc83981a6fbfa603a1a8c1a40b0931c5ae3450`; post-main CI `33956708698`, Security `33956708708`, and Docker Qualification `33956708755` are green. Repository branch-protection/ruleset enforcement was explicitly removed from this day-plan acceptance gate by maintainer decision on 2026-09-05.

## Acceptance amendment

Repository branch protection and repository rulesets are no longer required for completion of this day plan. This amendment changes only the repository-administration acceptance criterion; it does not remove or weaken the executable CI, security, architecture, Docker, coverage, or verification gates implemented by the plan.

With that criterion removed, all ten phases of the 2026-09-05 v0.1 scope-freeze and Week-1 preparation plan are complete.

No v0.1 product behavior was implemented by this day gate; it prepared executable contracts, fixtures, quality policy, and work sequencing for Week 1.
