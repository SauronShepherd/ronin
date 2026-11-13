# Qualification receipt — Terraform workspace isolation

- Date: 2026-11-13
- Implementation source: `7268d162`
- Focused Cloud Studio suite: **38 passed**.
- Full Python regression on the same implementation: **4554 passed, 80
  skipped, 0 failed** in 503.67 seconds.

For Terraform-backed Cloud Studio profiles, non-default workspaces now derive
validated, separate state directories beneath the configured Terraform root.
The default workspace remains backward-compatible. The implementation creates
the isolated directory before Terraform lifecycle calls and rejects unsafe
workspace names.

Boundary: this is local workspace-path isolation, not provider certification,
multi-user production tenancy, AWS Emulator support, or Public v1 family
qualification. Official status remains **0/13 (0%), NO-GO**.
