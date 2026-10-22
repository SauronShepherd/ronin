# ML drift report v1

`POST /v1/ml-studio/labs/{lab_id}/drift?workspace_id=...` compares two caller-supplied row windows against the Lab's explicitly numeric features. It requires `ml-studio:execute`.

The request contains `baseline_rows`, `current_rows`, and a `ronin.ml-drift-policy/v1` object. A policy has a stable ID, version from 1 through 2,147,483,647, and one threshold per numeric feature; the upper bound matches PostgreSQL's `INTEGER` column. Each window is limited to 100,000 rows. Every selected value must be a finite number in both windows. The API reports each window's count, mean, and population variance, plus signed current-minus-baseline deltas. Policies can be stored immutably by workspace and Lab with `POST /v1/ml-studio/labs/{lab_id}/drift-policies`, listed with `GET` on that route, and retrieved by exact policy ID/version at `/v1/ml-studio/labs/{lab_id}/drift-policies/{policy_id}/{version}`; the version path segment must be a canonical positive ASCII decimal integer without leading zeroes. Writes require `ml-studio:write`; reads require `ml-studio:read`. Reusing a version with different content or writing versions out of order returns a conflict. The drift form can load saved versions and save a policy before running a report.

Unknown Labs and missing exact policy versions return `404`; reusing a version with different content or writing a non-increasing version returns `409`.

`assessment.status` is `drifted` when the absolute mean or variance delta exceeds that feature's configured threshold; equality does not exceed the threshold. The API requires finite, non-negative thresholds and fails if any numeric Lab feature is unconfigured. It returns `ok` otherwise.

The report is an on-demand comparison, not a monitoring store. It does not retain input rows, discover windows, score models, trigger retraining, or promote models. It does not assess categorical drift, distribution shape beyond mean/variance, target performance, or fairness. Callers remain responsible for supplying authorized, comparable data windows.
