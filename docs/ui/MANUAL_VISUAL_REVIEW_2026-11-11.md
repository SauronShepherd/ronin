# Ronin Studio — manual visual review

Date: 2026-11-11  
Candidate: runtime/test `2406cd42`  
Reviewer mode: local Chromium, static server, no backend claims

## Scope and method

The shell was opened through the same static server used by the Playwright
suite. The visible viewport was inspected at `1440×900` and `390×844`; the
mobile shell was also checked at the responsive matrix widths. The review
covered the rail/topbar hierarchy, context presentation, home control plane,
fixed mobile navigation, keyboard discoverability and horizontal overflow.
`fullPage` screenshots were not treated as a shell-layout receipt because Ronin
uses an internally scrolling `main` region.

## Observed result

Passes for this review slice:

- no horizontal overflow was observed at the inspected widths;
- the desktop rail, topbar, context controls and action-first home surface have
  a coherent hierarchy and shared warm visual system;
- the mobile context now presents a readable `workspace / project` summary,
  while the full context remains available through `Edit`;
- the mobile navigation remains fixed without removing access to the page
  content, and additional bottom padding lets the control plane scroll clear of
  the bar;
- accessibility metadata and keyboard paths are covered by the candidate's
  automated Chromium suite (`172 passed / 33 explicit skips / 0 failed`).

## Open findings

This is evidence of inspection, not a human release approval. The following
still require a formal product/design sign-off:

1. Inspect the complete control plane while scrolling at 320, 390 and 520 px;
   verify that no last card or action is visually obscured by the fixed bar.
2. Review truncation of long workspace/project identifiers with realistic
   names. The candidate now provides both a native tooltip and an accessible
   full-value name; visual confirmation at 320px and 390px remains a human
   sign-off item.
3. Repeat the visual pass on every active Public v1 family journey and record
   screenshots against the same frozen release SHA.

The responsive matrix now also asserts that mobile `main` padding is at least
the fixed navigation height (`66px`), so the last visible content can scroll
above the navigation bar. This is a layout invariant, not a substitute for the
human inspection of long content.

Release consequence: these open findings keep the manual-visual-review gate
`qualification_pending`; they do not change the automated result, but they also
do not permit a GO decision. Public v1 remains `0/13` and **NO-GO**.
