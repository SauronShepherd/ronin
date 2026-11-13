# Qualification receipt — Docker worker and PostgreSQL current diagnostic

- Date: 2026-11-13
- Source checkout: `f0133645992e0a3c5c01c0f6335e86e01a69c94d`
- Qualification mode: **DIRTY-WORKTREE DIAGNOSTIC**; preserved user artifacts and the user-owned public status edit were present.
- Image: built from this checkout, `ronin:qualification`, digest `sha256:9f0bb9034b37afb69fc12565d46c529be9f44e0ca698b33b343fa2f323aaa7d0`.
- Selection: `docker_container_executor_real or worker_runtime_real or postgres`.
- Result: **8 passed, 19 deselected, 0 skipped, 0 failed** in 147.82 seconds.
- Coverage: Docker worker against PostgreSQL, SIGKILL reclaim/reuse, clean worker execution, container isolation/resource limits, memory-swap cap, and PostgreSQL/local-volume appliance backup restore.
- Evidence: `C:\Users\angel.alvarez\AppData\Local\Temp\ronin-docker-current-20261113081958`.
- Cleanup: runner completed service/container cleanup successfully.
- Boundary: strict frozen v0.1 acceptance was intentionally omitted by the filter; this diagnostic does not qualify the clean release candidate or close any complete Public v1 family.
