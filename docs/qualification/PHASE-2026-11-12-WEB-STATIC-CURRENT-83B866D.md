# Static Chromium web qualification — current candidate

**Date:** 2026-11-12  
**Candidate SHA:** `83b866d6f5a12eb17a62d3220ffdee6d5aa25def`

## Gate

Command, from `web-tests`:

```text
npm test -- --workers=1 --reporter=line
```

The configured command excludes tests tagged by the repository's live grep
filter. Result: **180 passed, 0 failed** in 5.9 minutes.

Coverage includes serious accessibility checks, responsive viewports,
keyboard navigation, route traversal across the Studio surfaces, connection
and server settings, SQL/QueryFlux, catalog/lineage, scheduler, ML, semantic,
streaming, synthetic and workspace/project journeys.

## Decision

Static Chromium web phase: **PASS** for this candidate. Live UI/API evidence
is maintained separately in the live-product receipt. Public v1 remains
**0/13 (0%) — NO-GO** until complete family and release gates close.
