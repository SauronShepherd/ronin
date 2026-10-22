# ML quality suite v1

`ronin.ml-quality-suite/v1` is a portable, versioned set of expectations that can be included in a PipelineIR v3 `quality_gate` configuration or sent to `POST /v1/ml-studio/labs/{lab_id}/quality`.

A suite contains an ID, version from 1 through 2,147,483,647, and 1 to 64 uniquely identified expectations. The upper bound matches PostgreSQL's `INTEGER` column. Persist suites with `POST /v1/ml-studio/labs/{lab_id}/quality-suites`; list versions with `GET` on that path and fetch an immutable version with `GET /v1/ml-studio/labs/{lab_id}/quality-suites/{suite_id}/{version}`. The version path segment must be a canonical positive ASCII decimal integer without leading zeroes. Every route requires `workspace_id`; read and write permissions are separated. A suite ID/version is immutable within a workspace and Lab, and each new version must increase monotonically. Each expectation names a Lab feature or target, a rule, severity (`warning` or `failure`), and a `value` field. Rules are:

Unknown Labs and missing exact suite versions return `404`; reusing a version with different content or writing a non-increasing version returns `409`.

- `not_null`: every row has a non-null value; `value` is null.
- `numeric`: every row has a finite number and is not a boolean; `value` is null.
- `min` / `max`: every row is a finite number meeting the inclusive bound in `value`.
- `min_distinct`: the column has at least the positive integer count in `value`, ignoring nulls.

The gate rejects references to columns outside the Lab. Failed warning expectations appear in `warnings`; failed failure expectations appear in `failures` and stop execution before preparation/training. Results include suite identity and each expectation outcome, and are retained in the durable quality-gate checkpoint with the execution.

Suite JSON is embedded in the pipeline digest when used for durable execution. Studio saves the suite in the Lab-scoped server catalog and also keeps the currently selected suite in browser session storage for the active session, keyed by both workspace and Lab so a same-named Lab in another workspace cannot inherit it. Use “Load saved suites” to retrieve versions from the server after a session ends. Use a new suite version when changing a saved policy.
