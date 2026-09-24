# Continuous Review Implementation Status

This file records which actionable recommendations from the continuous-review
bundle have been applied to the current Ronin OSS checkout. It is deliberately
separate from product status: implementation, local verification, external
qualification, and release approval remain different states.

| Review item | Action taken | Current state |
|---|---|---|
| ARC-001 / RONIN-BP-017 | Added `tools/capability_status.py` and `make capability-status-check` for the existing Public v1 machine ledger | implemented and locally verified |
| ARC-002 / RONIN-BP-001 | Added `tools/release_evidence.py` with fail-closed schema, commit binding, deterministic merge, and tests | implemented and locally verified |
| ARC-003 / BP-015/016 | Reconciled the ML review against the current source; `ronin.ml-lab/v1` already exists in `studio_ml.domain` | reconciled; product remains partial |
| EXT-001 | Existing manifest, capability, permission, route, and surface registries remain the authoritative extension boundary | implemented; further governance remains open |
| EXT-002 | Platform metadata already distinguishes readiness; capability ledger validation now rejects malformed status claims | implemented at validation layer |
| EXT-003 | Existing plugin/runtime/worker tests cover core contracts; the distributable `ronin-plugin-testkit` validates third-party plugin lifecycle and contribution contracts | implemented and locally verified |
| EXT-004 | ML product plugin and ML backend registry are separate modules/contracts in `studio_ml` | implemented |
| BLK-006 / BP-014 | Mutation gate remains at the configured policy and must be run on a POSIX-capable qualification runner | not closed by local unit tests |
| BLK-004 / BP-007 | Structural browser audit, installed-wheel Playwright smoke, standards-based axe accessibility checks and the conditional browser workflow are implemented | implemented and locally verified |
| BP-009 | Spark Connect adapter and qualification contract exist; exact real-runtime evidence remains separate | harness-ready |
| BP-008 | Migration providers exist; a dedicated `sdpstudio` compatibility contract must be declared before qualification | scope decision required |
| Execution architecture | Runtime-neutral backend contract added in `studio_execution.backend`; Docker/kind adapters can implement it without domain changes | phase 1 implemented |
| Kubernetes execution | `studio_execution.kubernetes.render_job` renders a restricted Job; local kind v1.36.1 created the Job, ran the worker, returned logs, and cleaned it up | locally qualified; `artifacts/kind-qualification.json` |
| Browser shell | Installed-wheel Chromium smoke traverses the published Studio routes with no console/request/CSP failures; installed-wheel axe checks report zero violations and zero layout failures | locally qualified smoke/accessibility gate; `qualification-evidence` remains generated evidence, not a release verdict |
| Cloud Studio | Floci is the local emulator qualification target; real cloud providers are outside OSS scope | locally qualified against Floci |

## Verification commands

```text
python -m tools.capability_status docs/product/public-v1-status.json
python -m pytest -q tests/test_capability_status.py tests/test_execution_backend.py
make release-evidence-validate BUNDLE=<bundle.json>
make cloud-studio-floci
```

## Remaining work that is genuinely implementation work

1. Add Docker and Kubernetes adapters for the runtime-neutral execution port.
2. Improve mutation survivors to the configured threshold on the qualification
   runner; do not lower the threshold.

## Scope rule

No item in this status file authorizes Ronin Pro, hosted cloud execution, or
provider-specific cloud connectivity. Such work is outside this repository's
OSS local-first target.
