# Demo ETL

This six-cell notebook performs two extracts, a fan-in join/aggregation, a quality check, and a publish step for the v0.1 acceptance journey.

Every executable cell is self-contained and idempotent. Ronin executes one clean container per cell, so notebook correctness must not depend on container-local `/tmp`, interpreter globals, or any other transient state surviving into a later cell. Dependencies express provenance and resume identity; a dependent cell reconstructs the small deterministic inputs it needs inside its own execution boundary.

This fixture intentionally favors a tiny deterministic workload over shared local files so the same notebook can be qualified through isolated Docker execution and later through process-level crash/reclaim without relying on hidden container state.

See ADR-V01-005 in `docs/automation/DECISIONS.md` for the record-level resume contract.
