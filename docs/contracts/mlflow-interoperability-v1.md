# MLflow interoperability contract v1

Ronin exchanges a bounded, metadata-only MLflow subset under
`ronin.mlflow-metadata/v1`. The payload contains one Ronin `Experiment`, one
`MLRunRecord`, an optional `RegisteredModelVersion`, and a declared flavor.
Supported flavors are `python_function` and `sklearn`; every other flavor is
rejected explicitly before import.

The run must reference the exported experiment and a model, when present, must
reference that run. Parameters, metrics, signatures, dataset revisions and
artifact digests are preserved through canonical JSON. The interchange never
loads pickle, code, environment archives, credentials, or provider artifact
URIs. Artifact bytes remain in the Ronin registry bundle/artifact store path and
are verified separately by their SHA-256 digest.

`export_mlflow_metadata()` and `import_mlflow_metadata()` are deterministic and
do not require an MLflow server. A provider adapter may use this envelope while
also implementing its own authenticated tracking transport, but server
availability must not be required to read the Ronin evidence.
