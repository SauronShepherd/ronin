# Phase receipt — installed Studio artifact smoke — 2026-11-12

## Candidate and artifact

- Source candidate: `6bfcf33546d8d6708c324209a38df9684e0ddc00`.
- Tested wheel: `ronin_studio-0.0.0-py3-none-any.whl`.
- Wheel SHA-256: `b31d7f580b6662c0a6b4c1aca6bcf6ea57421d684035e66e711fe92dcedfa1d7`.
- The smoke runner installed the wheel into an isolated temporary environment outside the checkout.

## Result

PASS: `tools.installed_studio_browser_smoke` exited 0.

- 25 Studio routes were loaded and checked.
- 3 bundled agent skills were valid: `ronin-core`, `ronin-data-engineering`, and `ronin-machine-learning`.
- Console errors: `0`.
- Failed network requests: `0`.
- CSP violations: `0`.
- Route smoke failures: `0`.

The `data` route exposed two matching headings, but its required smoke selector was unique and the runner reported no failure; this is retained in the raw JSON rather than hidden.

## Scope boundary

This is artifact-level browser/surface evidence. It does not prove the complete Public V1 end-to-end family journeys, provider certification, legal review, or release readiness. Verified release-qualified progress remains `0/13 (0%)`.

## Reproduction

```text
python -m tools.installed_studio_browser_smoke <wheel> --output <report.json>
```
