# Ronin visual navigation audit — 2026-10-23

## Result

The visual navigation audit is complete. After the responsive-navigation correction, a browser pass activated all 28 routes and checked 10 viewport sizes. That pass ran **10 consecutive times: 280 route activations, 100 viewport checks, 0 failures**. The complete Playwright suite also passed: **91/91 tests**.

## Coverage

- Control plane: all 28 links, repeated route transitions, one active link at a time, route heading presence, icon persistence, sidebar collapse and expansion.
- Responsive layout: 320×720, 390×844, 520×900, 521×900, 768×1024, 900×900, 901×900, 1024×900, 1280×900, and 1440×900. The document stays locked; the main surface owns vertical scrolling and compact navigation scrolls horizontally.
- Ronin Academy: all 9 tutorials completed on desktop, including progress, back, completion, three recommendations, exit, and Escape. All 9 tutorials were also walked on mobile; every step dialog and spotlight stayed within the viewport and highlighted a visible target.
- Keyboard and accessibility: modal focus entry, Tab and Shift+Tab containment, Escape exit, focus return, and keyboard selection of data pipeline nodes.
- Command palette: all 28 routes appear, search finds Quality Studio, and Enter opens the selected route.
- Standalone studios: Cloud Studio and Data Engineering Studio on desktop and mobile, including graph node creation, connecting nodes, validation error presentation, and internal scroll behavior.
- Additional visual surface: Throw Your Threads on desktop and mobile; all three scene choices are visible without page overflow.
- Console: no browser errors or warnings were recorded during the final route sweep.

## Findings fixed

1. At narrow viewport and zoom sizes, the control plane retained a side rail and left the main content cramped. At 900px and below the app shell now uses one column, with the navigation in a fixed bottom rail.
2. The compact bottom navigation now hides the rail header and subtitle, keeps route icons visible, and scrolls horizontally inside the rail.
3. Tutorial steps could spotlight hidden desktop controls on mobile, and the modal did not contain or restore keyboard focus. Hidden targets now fall back to visible controls, the dialog receives initial focus, Tab stays in the dialog, Escape exits, and focus returns to the launch control. The step counter is announced politely.
4. Quality Studio controls were uneven at desktop sizes and the optional execution reference placeholder was clipped on mobile. The form now uses a six-column desktop layout, a two-column mobile layout, and a full-width row for the optional reference.
5. Quality Studio used a 100ms interval to wait for its dynamically rendered form. This was replaced with a `MutationObserver` so controls mount when the view changes without polling continuously.
6. The command palette listed only part of the navigation. It now uses `routes.json`, includes all 28 routes, and has labels for the remaining route IDs.
7. The standalone Data Engineering canvas lacked the CSS class needed to render its graph and had a misspelled visible title. The canvas is styled, edges are drawn between connected nodes, and nodes can be selected from the keyboard with focus preserved.
8. Cloud Studio and Data Engineering Studio could clip lower content on mobile because their page body was locked while the main area had no internal scroll. Their mobile main areas now scroll within the viewport.
9. The browser test server handled requests serially, so Chromium’s parallel module loads could intermittently fail with `ERR_CONNECTION_REFUSED` and leave the navigation rail unmounted. Replaced it with a threaded server with a larger request queue; ten repeated navigation-and-viewport passes then completed without failed requests.

## Verification limits

The browser used a static local HTTP server, not Ronin’s API. Backend-dependent screens therefore display their expected unavailable-service state; the UI rendered structured unavailable-service errors. This audit verifies navigation and visual behavior, not backend contracts or real data operations. No unit, integration, or Docker suite was run as part of this visual audit.

## Changed files

- `web/styles/layout.css`
- `web/styles/components.css`
- `web/js/app.js`
- `web/js/features.js`
- `web/js/quality-studio.js`
- `web/js/tutorials.js`
- `web/js/command-palette.js`
- `web/js/i18n.js`
- `web/data-enginerring-studio.html`
- `web/data-enginerring-studio.css`
- `web/data-enginerring-studio.js`
- `web/cloud-studio.css`
- `web-tests/playwright.config.mjs`
- `web-tests/static_server.py`
- `web-tests/tests/route-traversal.spec.mjs`
- `web-tests/tests/responsive-matrix.spec.mjs`
