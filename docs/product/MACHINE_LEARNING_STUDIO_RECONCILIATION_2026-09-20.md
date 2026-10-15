# Machine Learning Studio Reconciliation

**Purpose:** reconcile the continuous-review claims with the current Ronin OSS
checkout. This document is an evidence map, not a release claim.

## Finding

The review package was generated from an older repository snapshot. The current
checkout already contains the first `ronin.ml-lab/v1` contract and substantially
more of the proposed ML surface than the review describes. The correct action is
to keep the product status conservative while avoiding duplicate implementations.

## Evidence map

| Review claim | Current source | State | Evidence boundary |
|---|---|---|---|
| Lab identity and schema | `python/studio_ml/domain.py:Lab`, `LAB_SCHEMA` | implemented | strict payload shape, canonical JSON, domain tests |
| Pipeline IR | `python/studio_ml/domain.py:PipelineIR` | implemented | acyclic dependency validation and canonical serialization |
| Local tabular runtime | `python/studio_ml/runtime.py` | implemented | deterministic training, canonical non-executable artifacts, digest-verified prediction |
| ML backend abstraction | `python/studio_ml/backends.py` | implemented | backend registry, capabilities and local backend |
| Experiment orchestration | `python/studio_ml/orchestration.py`, `runner.py` | implemented | bounded local execution and persisted snapshots |
| Optimization | `python/studio_ml/optimization.py` | implemented | bounded trial/search contracts |
| Quality/provenance | `quality.py`, `provenance.py`, `service.py` | implemented | profile, run, evaluation, artifact and registry contracts |
| Local persistence | `sqlite.py`, `postgres.py`, `services.py` | partial | adapters exist; full Public v1 lifecycle/UI remains partial |
| Remote adapters | `remote.py` | partial | provider-neutral adapter contracts exist; external runtime qualification remains separate |
| Product plugin/API surface | `plugin.py` | partial | plugin surfaces exist; complete Public v1 authoring journey is not claimed |
| Advanced algorithms and feature engineering | current runtime and domain packages | partial | only the implemented algorithm/task matrix is supported |

## Contract decision

`ronin.ml-lab/v1` is the canonical Lab contract. It must remain separate from:

1. the `ml-studio` product plugin and HTTP/UI surfaces; and
2. pluggable ML execution backends.

The product plugin owns lifecycle and user-facing operations. Backend adapters
own capability negotiation, training/prediction/cancellation, and runtime
specific evidence. No provider SDK may be imported into the canonical domain.

## Status corrections

The following claims must not be made without stronger evidence:

- that all modules named by the full specification are implemented;
- that remote providers are qualified;
- that ML Studio is Public v1 complete;
- that a registered model is deployable to a network serving endpoint;
- that local algorithm coverage implies production ML support.

The Public v1 ledger should keep AI/ML/MLOps as `partial` and describe the
implemented local contracts precisely.

## Acceptance tests for future slices

Every new ML slice must provide:

- a versioned canonical schema;
- strict unknown-field and invalid-value handling;
- deterministic serialization and identity;
- artifact digest/provenance binding;
- cancellation/timeout behavior where execution is involved;
- a backend capability/unsupported-pair test;
- a status transition only after source, test, and qualification evidence exist.

## Implementation order

1. Keep the current Lab/Pipeline/runtime contracts stable.
2. Complete the product/API lifecycle around those contracts.
3. Add backend capability negotiation and explicit unsupported-pair errors.
4. Add bounded experiment/search features behind the same evidence model.
5. Add remote adapters only as isolated, separately qualified implementations.
