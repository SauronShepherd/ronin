# Qualification receipt — installed artifact after OpenLineage change

- Date: 2026-11-13
- Source checkout: `4d9316e1e00c860fa3c826a4677f6693937c8b62`
- Runner: `python tools/artifact_qualification.py --output C:\Users\angel.alvarez\AppData\Local\Temp\ronin-artifact-qualification-dedup-20261113074832.json`.
- Scope: isolated wheel/sdist build and installation outside the checkout, artifact identity/origin checks and installed package contract tests.
- Result: **90 passed, 0 failed** in 2.37 seconds.
- Boundary: this verifies the PyRonin artifact lane; it does not qualify the complete RONIN platform release, license approval, external providers or Public v1 families.
