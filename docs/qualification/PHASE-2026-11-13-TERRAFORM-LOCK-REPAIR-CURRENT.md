# Qualification receipt — generated Terraform lock repair

- Date: 2026-11-13
- Fix: generated Cloud Studio workspaces discard only an incomplete `.terraform.lock.hcl` that lacks the exact AWS provider `6.65.0` selection, then initialize with `-upgrade`; valid locks remain untouched.
- Focused Cloud Studio gate: **42 passed, 0 failed**; Ruff clean.
- Full Python gate after the fix: **4563 passed, 80 skipped, 0 failed** in 399.56 seconds.
- CI evidence: runs `43453980958` and `43456756709` still failed at plan with the incomplete-lock symptom; the next run on this fix is required for closure.
