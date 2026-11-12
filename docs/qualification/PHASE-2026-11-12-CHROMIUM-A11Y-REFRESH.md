# Phase receipt — Chromium and accessibility refresh — 2026-11-12

## Candidate

- Source candidate under test: `20a094efcf600a38d4ed14d2ff157c196dc17e25`.
- Test command: `npm test -- --workers=1` from `web-tests`.

## Evidence

- Chromium suite: **180 passed**, 0 failed, 0 skipped, duration 15.9 minutes.
- The suite includes route accessibility checks, responsive matrix, keyboard/context behavior, Studio workbench journeys, ML/SQL/streaming/project/workspace flows, and route traversal.
- The installed-artifact automated accessibility audit after the contrast fix separately returned **0 violations, 0 layout failures**, exit code 0.

## Result

PASS for the full static Chromium and installed-artifact automated accessibility refresh. The evidence is bound to this source candidate for the browser run; release publication still requires the complete candidate gate aggregation, legal review, and remaining human/manual gates. Public V1 remains `0/13 (0%)`.
