# Contributing to Cloud Studio

## Add a resource type

1. Add a provider-neutral key to `python/studio_cloud/engine.py`.
2. Define its label, category, Terraform mapping, property schema, and backend matrix.
3. Add scalar validation rules only; never evaluate user-provided expressions.
4. Add export/import round-trip tests.
5. Add in-memory lifecycle tests.
6. Add Floci/LocalStack compatibility evidence when the service is supported.
7. Update `CLOUD_STUDIO_SPECIFICATION.md` and the compatibility table.
8. Run Ruff, Python tests, the web audit, and Chromium E2E.

## Add a backend

1. Implement `EmulatorBackend` in `python/studio_cloud/backends.py`.
2. Provide `health`, `plan`, `apply`, `refresh`, and `destroy`.
3. Bound every external operation with a timeout.
4. Capture stdout/stderr and return actionable errors.
5. Isolate workspace files and state.
6. Keep credentials and tokens in environment variables only.
7. Add Compose or local startup instructions.
8. Add unit and integration tests.

## UI changes

- Keep the visual surface dependency-light unless a frontend dependency is explicitly approved.
- Add keyboard behavior and visible focus for every new interactive control.
- Preserve JSON import/export compatibility.
- Extend `tools/cloud_studio_web_audit.mjs` for new required controls.
- Extend `tools/cloud_studio_e2e.py` for user-visible interactions.

## Required checks

```text
ruff check python/studio_cloud tests/test_cloud_studio.py
python -m pytest tests/test_cloud_studio.py -q
node tools/cloud_studio_web_audit.mjs
python tools/cloud_studio_e2e.py
```
