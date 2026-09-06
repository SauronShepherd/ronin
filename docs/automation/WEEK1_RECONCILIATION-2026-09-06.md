# Week-1 reconciliation — 2026-09-06

**Exact starting main:** `069023ea65923ac16640d139088f0ea1fc1358b5`

The original Week-1 queue has twelve numbered items. Four are already delivered, seven remain untouched, and PR-09 is partially delivered. Therefore eight items remain unfinished; the earlier phrase “seven remaining” counts only untouched items and must not be interpreted as eight-minus-one completed work.

| Planned item | Canonical issue | State on 2026-09-06 |
|---|---:|---|
| PR-01 terminal cancellation evidence | #75 | **done** — implementation/evidence landed via #67 |
| PR-02 reap runner + preserve truncation prefix | #76 | open |
| PR-03 memory-swap/ulimits/units | #77 | open |
| PR-04 tested isolation by default | #78 | open |
| PR-05 quality perimeter | #79 | **done** — delivered via #74 |
| PR-06 tier coverage/Python 3.12/hash lock | #80 | **done** — delivered via #74 |
| PR-07 bounded/redacted failures + runtime comparison | #81 | open; comparator decision resolved by ADR-V01-006 |
| PR-08 close pure-domain `os` exemption | #82 | **done** — delivered via #74 |
| PR-09 stable indexes/performance budgets | #83 | **partial** — #89 improved several catalogs; `Node.param` and `OperatorCatalog.get` remain |
| PR-10 async event sink | #84 | open |
| PR-11 T1 properties | #85 | open |
| PR-12 SDK resilience | #86 | open |

## Capacity reassignment

Capacity freed by completed PR-01/05/06/08 is assigned explicitly to **#99 (49a)**: pure Job/Run/Attempt lifecycle plus the `JobStore` Protocol. This is the next critical-path platform slice after the 2026-09-06 infra/docs throughput PR lands.

PR-09 remains part of Week 1 rather than being counted as complete. Its completion claim requires committed measurement evidence proving the remaining hot paths improve end to end.

## Week-1 execution order after reconciliation

1. P1 execution trust defects #76 and #78.
2. P1 runtime contract work #81/#50 now that the version decision exists.
3. Critical-path #99 using the freed capacity, provided no higher release-trust defect makes a green check lie.
4. Remaining Week-1 P2 slices #77, #83, #84, #85, #86, bundling same-domain work only where qualification remains coherent.

This reconciliation does not move E3-E10 into scope and does not weaken the fifteen-step release acceptance invariant.
