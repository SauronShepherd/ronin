# Migration certification evidence

`tools/migration_certification.py` validates evidence with schema
`ronin.migration-certification/v1` for the four bounded profiles: Fabric,
Databricks, Foundry/AIP and Dataiku DSS.

Certification is fail-closed. Evidence must bind source inventory, translation
report and Bundle round-trip with SHA-256 digests, report successful execution,
and include all six classification counters (`exact`, `translated`, `partial`,
`passthrough`, `unsupported`, `manual_decision`). The `source_object_ids` array
must contain unique non-empty identities and its length must exactly equal the
sum of the counters. This prevents an omitted or multiply classified source
object from being hidden by aggregate counts.

Local fixture qualification validates translation and redaction behavior; a
provider certification still additionally requires authenticated discovery,
target execution and exact evidence from the selected provider environment.
