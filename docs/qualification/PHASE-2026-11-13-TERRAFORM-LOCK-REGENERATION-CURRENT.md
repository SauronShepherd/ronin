# Qualification receipt — deterministic generated Terraform lock regeneration

- Date: 2026-11-13
- Fix: isolated generated Terraform workspaces regenerate `.terraform.lock.hcl` before `init -upgrade`; the backend does not manage user-authored Terraform directories.
- Focused Cloud Studio gate: **42 passed, 0 failed**; Ruff clean.
- Full Python gate: **4563 passed, 80 skipped, 0 failed** in 326.81 seconds.
- CI diagnostic addressed: incomplete lock selections observed in runs `43453980958`, `43456756709` and `43459854207`.
- Boundary: CI must execute successfully on this new SHA before the Build Plan CI item is marked complete.
