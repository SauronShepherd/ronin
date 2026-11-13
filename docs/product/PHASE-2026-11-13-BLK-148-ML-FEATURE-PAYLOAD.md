# BLK-148 — ML Feature Studio payload contract

Date: 2026-11-13  
Status: **PASS for the UI payload contract slice; installed end-to-end browser qualification remains open.**

## Finding

The ML Feature Studio form emitted `columns`, omitted required `name`, `project_id`, `features`, and `transform`, and serialized `version` as a string. That shape is rejected by `FeatureDefinition.from_payload`, whose contract requires exact keys and `{column, role}` feature entries.

## Change

`web/js/ml-features-studio.js` now collects the required fields and posts the canonical `ronin.ml-feature/v1` payload, including numeric `version`, `features`, and `transform`. The web asset regression test asserts the required markers and rejects the obsolete `columns` payload.

## Evidence

- `tests/test_web_package_assets.py::test_ml_studio_exposes_feature_definition_lifecycle`: passed.
- `tests/integration/test_ml_studio_http.py`: passed (3 tests).
- Combined focused result: **4 passed in 6.37s**.
- `node --check web/js/ml-features-studio.js`: passed.
- Ruff check/format for the changed Python test: passed.
- Studio web budget ratchet updated to the measured CI asset size `2167935` bytes; `python tools/studio_budget.py --check` passes locally.
- Commit/push: `c30f449e`.

## Boundary

This qualifies the source payload contract only. A clean-wheel installed browser journey with real HTTP, negative responses, accessibility review, and exact artifact evidence remains open. Public v1 remains **0/13 families, 0%, NO-GO**.
