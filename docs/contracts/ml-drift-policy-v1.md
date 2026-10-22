# ML drift policy v1

`ronin.ml-drift-policy/v1` is an immutable, workspace and Lab scoped catalog
entry used by the numeric drift report endpoint.

```json
{
  "schema": "ronin.ml-drift-policy/v1",
  "id": "customer-drift",
  "version": 1,
  "thresholds": [
    {"feature": "monthly_spend", "mean_delta": 10.0, "variance_delta": 100.0}
  ]
}
```

`id` is trimmed text of at most 256 characters. `version` is a positive
integer from 1 through 2,147,483,647, matching the PostgreSQL `INTEGER`
bound. A policy contains one threshold for every numeric feature declared by
the Lab and no duplicate features. Thresholds are finite, non-negative
numbers and compare absolute changes in the feature mean and population
variance. Missing, extra, or duplicate numeric features are rejected before
the policy is stored or used.

Policies are immutable within `(workspace_id, lab_id, id, version)`. Reusing
an existing version with different content, or writing a version that does
not increase monotonically for the same ID, returns a conflict. The catalog
is available through:

- `POST /v1/ml-studio/labs/{lab_id}/drift-policies` (`ml-studio:write`)
- `GET /v1/ml-studio/labs/{lab_id}/drift-policies` (`ml-studio:read`)
- `GET /v1/ml-studio/labs/{lab_id}/drift-policies/{policy_id}/{version}` (`ml-studio:read`)

Every request supplies `workspace_id`. Version path segments use canonical
positive ASCII decimal notation without leading zeroes. Unknown Labs or
policy versions return `404`; malformed policies and non-canonical versions
return `400`.

Saving a policy does not retain row data or start a drift calculation. The
policy is embedded in a durable PipelineIR only when a caller explicitly
selects it for an execution; changing thresholds requires a new version.
