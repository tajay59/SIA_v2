# ADR-0010: Vue 3 + TypeScript + Vuetify 4 + file-based routing + Zod 4

- Status: Accepted (2026-11-06)
- Related: TRD (frontend stack), DESIGN_BRIEF §8, APD

## Context
Both legacy frontends (SHOP, SIA) are Vue 3 in plain JavaScript. The rebuild needs type safety, accessible components, a light/dark theme from tokens, and API clients that can't drift from the contract.

## Options
1. **Keep Vue 3; add TypeScript, Vuetify 4 (Material 3), file-based routes and Zod**: same framework as legacy, rich accessible components.
2. **React + MUI**: large ecosystem; a full rewrite in a framework new to the project.
3. **Vue + a headless kit and own styling**: more control; much more component work for one developer.

## Decision
Option 1 for SHOP and SIA, sharing `packages/web-app` (auth, layout, shared components) and `packages/web-ui` (theme). Routes come from `src/pages` (typed router). API clients are generated from OpenAPI; Zod validates forms and responses; Pinia holds state.

## Consequences
- One component system and theme in both apps; Material 3 maps cleanly to the Android app (DESIGN_BRIEF).
- Vuetify defaults are themed centrally (solo-inverted fields, M3 pill buttons); quirks are handled in shared CSS (`base.css`, `console.css`).
- Playwright + axe run every journey in Chromium, Firefox, WebKit and at 360 px.
