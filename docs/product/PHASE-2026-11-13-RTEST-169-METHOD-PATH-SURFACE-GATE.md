# RTEST-169 — Method/path surface gate

Date: 2026-11-13  
Status: PASS for the static method/path gate; clean-wheel and dynamic-plugin qualification remain open.

## Change

`tools/studio_surface.py` now compares Studio invocations against the published contract using both HTTP method and parameterized path. A path that exists only under another verb is rejected as unpublished. The matcher is shared by the unknown-operation and matched-operation calculations.

## Evidence

- `tests/test_studio_surface.py` and `tests/test_route_consistency.py`: **4 passed**.
- `python -m tools.studio_surface`: **128/241 published operations matched**, above the existing ratchet.
- `python -m tools.route_consistency`: **199 operations consistent**.
- Ruff on changed files: **clean**.
- `tests/test_plugin_clean_room.py::test_first_party_plugins_discover_from_clean_main_wheel`: **passed** against a freshly built `ronin_studio-0.0.0-py3-none-any.whl`, installed into an isolated target outside the checkout; all 7 first-party entry-point manifests were discovered with `-S` and `PYTHONNOUSERSITE=1`.

## Boundary

This does not close the full RTEST-169 task: dynamic third-party/plugin inventory and the complete negative operation matrix still require their dedicated release lane. The first-party clean-wheel discovery slice is now evidenced. No Public v1 family is promoted.

## Progress

- Static method/path gate slice: **100% evidenced**.
- First-party clean-wheel discovery slice: **100% evidenced**.
- RTEST-169 overall: **partial; dynamic-plugin inventory and full negative matrix remain open**.
- Official Public v1: **0/13 families, 0%, NO-GO**.
