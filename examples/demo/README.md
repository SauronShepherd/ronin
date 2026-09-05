# Demo ETL

This six-cell notebook performs two extracts, a fan-in join/aggregation, a quality check, and a publish step for the v0.1 acceptance journey.

Executable cells are deliberately idempotent and communicate through files so a clean replacement container can resume from durable per-cell results without restoring interpreter state.

See ADR-V01-005 in `docs/automation/DECISIONS.md` for the record-level resume contract.
