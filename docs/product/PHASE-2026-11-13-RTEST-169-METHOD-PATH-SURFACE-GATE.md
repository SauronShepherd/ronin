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

## Boundary

This does not close the full RTEST-169 task: dynamic third-party/plugin inventory, clean-wheel discovery, and the complete negative operation matrix still require their dedicated release lane. No Public v1 family is promoted.

## Progress

- Static method/path gate slice: **100% evidenced**.
- RTEST-169 overall: **partial; remaining clean-room qualification not-run**.
- Official Public v1: **0/13 families, 0%, NO-GO**.
