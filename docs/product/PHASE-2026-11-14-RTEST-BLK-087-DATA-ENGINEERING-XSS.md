# RTEST-BLK-087 — Data Engineering dynamic rendering

Date: 2026-11-14  
Status: **PASS for the source-rendering security slice; installed candidate and full Public v1 family qualification remain open.**

## Finding

The Data Engineering Studio rendered pipeline node IDs, serialized pipeline JSON, SQL history and saved-query names through dynamic `innerHTML` without escaping. These values can originate from editable pipeline/query state and must not become markup.

## Change

`web/js/data-engineering-studio.js` now applies the existing `esc()` helper to node IDs, pipeline JSON, SQL history labels and saved-query names before interpolating them into markup. The change preserves the existing UI behavior and does not alter API payloads.

## Evidence

- `tests/test_web_package_assets.py::test_data_engineering_dynamic_markup_escapes_untrusted_values`: passed.
- `tests/test_web_package_assets.py`: **11 passed**.
- `node --check web/js/data-engineering-studio.js`: passed.
- Data Engineering Chromium journeys: **11 passed in 23.0s**.
- Full Python suite: **4568 passed, 80 skipped, 0 failed in 685.39s**; skips are documented external/opt-in lanes.
- CI exact candidate `43566224630`: Python 3.11 success, Python 3.12 success, Chromium non-live success, Cloud Studio Terraform/Floci success.
- Published source SHA: `4cb4465b8268c21a3149a1640ad0ccb101c3687b`.

## Boundary

This closes only the source-rendering security slice. It does not qualify the installed wheel, external providers, human accessibility review or any Public v1 family. Public v1 remains **0/13 families, 0%, NO-GO**.
