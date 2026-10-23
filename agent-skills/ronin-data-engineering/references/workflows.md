# Data Engineering workflow contract

Use this order unless the task requires a read-only subset:

1. doctor
2. validate project
3. connector capabilities
4. discover/preview
5. connector plan
6. project target plan
7. submit with idempotency
8. status/logs
9. evidence
10. checkpoint-health where connector state is relevant

Known documented connector CLI group: `capabilities`, `discover`, `preview`, `plan`, `checkpoint-health`.

Failure handling:
- Command absent: report compatibility gap.
- Validation failure: do not submit.
- Preview exceeds available bounds: reduce scope rather than materialize unbounded data.
- Submission uncertain: query jobs/status using the same logical identity before retrying.
- Evidence missing or partial: report execution as unqualified, not successful-by-assumption.
