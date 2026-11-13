# Qualification receipt — Cloud Studio Terraform CI workflow prepared

- Date: 2026-11-13
- Change: `.github/workflows/quality.yml` now defines a pinned Terraform/Floci job.
- Pinned toolchain: Terraform **1.13.5**, `hashicorp/setup-terraform` v3.1.2 at commit `b9cd54a3c349d3f38e8881555d616ced269862dd`, and the repository-pinned Floci image.
- Workflow contract: installs the hash-locked Python environment, starts isolated Floci, runs the official qualification runner with Terraform, and always removes the compose project and volumes.
- Static verification: workflow parsed successfully with PyYAML.
- Boundary: this receipt records workflow preparation, not a GitHub Actions execution. The Build Plan CI item remains open until a real run produces a passing receipt.
