# Qualification receipt — Terraform init lock recovery

- Date: 2026-11-13
- Fix: Terraform backend initialization now runs `init -upgrade -backend=false -input=false` within exact provider/version constraints, recovering stale or incomplete dependency lock selections before `plan`.
- Focused Cloud Studio gate: **42 passed, 0 failed**; Ruff clean.
- Full Python gate after the fix: **4563 passed, 80 skipped, 0 failed** in 715.73 seconds.
- CI diagnostic that motivated the fix: run `43453980958` reached Floci health and `validate`, then failed at `plan` with an inconsistent dependency lock file.
- Boundary: a new CI run is required before closing the CI plan item or claiming Floci qualification.
