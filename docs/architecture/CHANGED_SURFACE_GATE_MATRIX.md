# Changed-surface gate matrix

This repository contains changes that span more than one product area. A
review or release claim must therefore use the gate for the affected subsystem
instead of treating an unrelated green workflow as qualification.

The machine-readable inventory is produced with:

```text
python -m tools.changed_surface <base> <head> --output changed-surface.json
```

The command fails closed when a path cannot be assigned to exactly one
subsystem. The resulting `subsystems` object is the source of truth for the
scope review.

| Subsystem | Required gate(s) | Evidence boundary |
| --- | --- | --- |
| packaging | `python -m build`, installed wheel/sdist smoke | Only installed artifacts, never the checkout |
| runtime | `pytest`, import smoke, architecture gate | Python 3.11 and 3.12 |
| plugin | plugin inventory, plugin contract tests, import smoke | Registry and worker boundaries |
| data-engineering | unit/integration tests, async collection, browser route smoke | Compilation, execution, lineage and evidence |
| ml | ML contract/integration tests, provider capability tests | Local/runtime-backed claims only |
| migration | qualification profiles and migration certification evidence | Every object classified |
| ui | asset graph, Chromium installed-artifact smoke, axe accessibility | Wheel and sdist, not source assets |
| qualification | release evidence, Docker/PostgreSQL, mutation and security gates | Exact candidate and artifact identity |
| documentation | status consistency and review of linked contracts | No historical SHA presented as current |

Publication is not an independent changed-surface category: it is gated by
the `qualification` evidence and may only publish the exact artifact or image
that passed that evidence. Mutable aliases (`dev` and `edge`) are deliberately
separate from immutable semantic release identities.

## Review rules

1. The base and head must be recorded before reviewing the diff.
2. Every changed path must map to one subsystem; ambiguity is a failure.
3. Each non-empty subsystem must have at least one executable gate above.
4. A green workflow is evidence only for the subsystem and candidate it
   actually exercised.
5. Release and publication changes require exact source/artifact binding and
   cannot be hidden under a narrower change title.
