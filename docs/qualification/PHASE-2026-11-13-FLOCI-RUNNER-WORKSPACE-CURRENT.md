# Qualification receipt — Floci runner workspace preflight

- Date: 2026-11-13
- Change: the qualification runner now creates nested Terraform workspace directories before backend initialization.
- Focused gate: `python -m pytest -q tests/test_cloud_studio_floci_qualification.py tests/test_cloud_studio.py` — **42 passed, 0 failed**.
- Static gate: Ruff on the runner and focused tests — **passed**.
- Boundary: Docker Desktop was unavailable during the real provider attempt; this receipt proves runner preflight behavior only and does not claim Floci qualification.
