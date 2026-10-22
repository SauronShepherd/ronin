# ML model card v1

`GET /v1/ml-studio/models/{model_id}/{version}/card?workspace_id=...` returns `ronin.ml-model-card/v1` for a registered model version.

The card contains immutable model identity, artifact digest and reference, input/output signature, and source-run provenance. When the source run is available, it also includes the governed dataset revisions, effective parameters, recorded metrics, execution reference, and source revision. The feature list is derived from the model input signature.

`intended_use.task` is copied from the source run's recorded task when present. The accompanying statement limits use to the declared signature and reviewed evaluation evidence; it is not a claim of production suitability. Fairness is explicitly `not_assessed` because the current run contract does not attach protected-group evaluation evidence. Owner is `null` until an owner identity is recorded in the run contract. Missing source-run evidence is represented by empty dataset/metric collections, null execution/revision references, and a limitation.

The card does not infer fairness, owner identity, or suitability from model metrics. Promotion remains a separate authorized operation with its own reason and audit record.
