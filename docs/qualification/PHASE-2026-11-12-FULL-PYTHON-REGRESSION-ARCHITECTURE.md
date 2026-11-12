# Qualification receipt — full Python regression after QueryFlux composition

- Date: 2026-11-12
- Source checkout before receipt commit: `0ad125f439d4d9f429a88a1b52b739815c90eeb7`
- Initial regression: `4539 passed, 79 skipped, 1 failed`; the failure was an architecture-gate omission, not a runtime failure: `studio_cli` imported `studio_query_engine` for the QueryFlux composition but `tools/architecture_gate.py` did not declare that allowed dependency.
- Remediation: added `studio_query_engine` to the explicit `studio_cli` dependency contract.
- Focused verification: `tests/test_architecture_contracts.py` — **19 passed**; direct architecture gate passed.
- Full regression after remediation: **4540 passed, 79 skipped, 0 failed** in `329.38s` (`python -m pytest -q`).
- Boundary: skips are environment/provider-qualified cases and are not counted as passes; this receipt is regression evidence and does not qualify all Public v1 capability families.
