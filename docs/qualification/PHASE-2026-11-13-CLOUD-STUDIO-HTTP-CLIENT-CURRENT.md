# Qualification receipt — Cloud Studio HTTP client

- Date: 2026-11-13
- Scope: external `HttpEmulatorBackend` request execution, timeout/endpoint validation and RFC 9457-compatible problem propagation.
- Focused gate: `python -m pytest -q tests/test_cloud_studio.py` — **29 passed, 0 failed**.
- Static gate: Ruff on `python/studio_cloud/backends.py` and `tests/test_cloud_studio.py` — **passed**.
- Implementation: `apply` and `plan` POST JSON topology payloads; `refresh` GETs; `destroy` POSTs; non-2xx JSON problem bodies become structured `HttpBackendError` with status and problem document.
- Boundary: this proves the client contract with an isolated HTTP stub; it does not claim external provider qualification or Public v1 family release qualification.
