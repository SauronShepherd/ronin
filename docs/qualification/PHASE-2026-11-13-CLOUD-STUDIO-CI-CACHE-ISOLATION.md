# Qualification receipt — CI Terraform cache isolation

- Date: 2026-11-13
- Observation: GitHub Actions runs `43453980958`, `43456756709` and `43459854207` reached Floci health/validate but failed at plan with an incomplete dependency lock despite local fresh-workspace initialization passing.
- Change: the CI job now uses a dedicated `TF_PLUGIN_CACHE_DIR` under `${{ runner.temp }}` and removes/recreates `.tmp/cloud-studio-ci` before qualification.
- Static verification: workflow parses successfully with PyYAML.
- Boundary: this is a corrective CI preparation receipt; the CI plan item remains open until the next real Actions run passes.
