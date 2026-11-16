# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users
- **SIA (staff app, `web/sia`):** CIMH stores staff and admins. Desk work (request queue, quotes, agreements, product and settings admin, account approvals) and floor work (scan to stow, pick, relocate, issue/return, labels) on desktops and phones. Admins must use MFA.
- **SHOP (customer store, `web/shop`):** external Caribbean meteorological and hydrological organisations (and CIMH staff, who browse but cannot request) looking for instrument and equipment spares. They browse the catalogue, build a request, accept a quote by uploading a signed agreement, and follow it to delivery.

## Product Purpose
CIMH Stores replaces the legacy SIA/SHOP apps for the Caribbean Institute for Meteorology and Hydrology. It tracks every spare unit on CIMH shelves and runs the request flow from cart to delivery. Success: staff always know what is where and what to do next; customers get spares without email back-and-forth.

## Positioning
A regional institute's own spares store, not a webshop: no prices on product pages, no payments, quotes priced per request (CIMH stock or supplier, per line), acceptance by signed agreement, and Pro Bono (free) items for member organisations.

## Operating Context
- Paid request: SUBMITTED → QUOTING → QUOTED → AWAITING_AGREEMENT → ACCEPTED → PURCHASING → SHIPPED → DELIVERED. Pro Bono: SUBMITTED → APPROVED → PICKING → SHIPPED → DELIVERED.
- Registration: email verification, then admin approval (`@cimh.edu.bb` accounts skip approval).
- Currency BBD or USD per request; quotes valid 30 days; carriers FedEx, DHL, hand delivery with tracking typed in by hand.
- Barcode/QR scanning (USB/Bluetooth scanners act as keyboards); the Android app (SIA Mobile) covers camera scanning.
- Product types: MET, RAD, EQUIP, SUPP, MISC, PRO. ~83 products and ~700 units today; built for 1M registered users.

## Capabilities and Constraints
- Full screen list and journeys: `docs/APD.md` (S-nn SHOP, A-nn SIA); features: `docs/PRD.md`.
- Stack fixed: Vue 3 + TypeScript + Vuetify 4, file-based routing, Pinia, Zod; shared components in `packages/web-app`.
- Customers never see prices, costs or serial numbers on product pages.
- Page structure is **not** bound to the legacy apps any more (owner, 2026-11-11): keep every function and piece of content, but pages may be reorganised.
- Three roles only: admin, staff, user.

## Brand Commitments
- Name "CIMH Stores"; staff app "SIA"; Pro Bono (never "NCI").
- Logo blue `#0084C8` (not for normal text, 4.09:1); interactive primary `#006FA8` light / `#5CC2FF` dark; Pro Bono badge `#F5C400` with ink text only.
- Fonts Inter + JetBrains Mono, self-hosted. `docs/DESIGN_BRIEF.md` is the current visual reference (no official CIMH brand guide exists); a redesign may replace its look but must keep these commitments.

## Evidence on Hand
- Real catalogue data and product photos (staging holds migrated legacy data; local dev DB holds generated test data).
- Logo and legacy images in `packages/web-app/src/assets/legacy/`; SHOP home hero slot `web/shop/src/assets/hero/` (image still to come from the owner).
- No testimonials, statistics or partner claims exist; do not invent them.

## Product Principles
1. The next action is obvious: every request and unit shows its state and what to do now.
2. Scanning is first-class: scan fields accept Enter, never lose focus to the UI.
3. Trust over sales: no prices or pressure; clear status, dates and documents.
4. One product, two surfaces: SHOP and SIA share components and tokens.
5. Works on a phone in a storeroom as well as on a desk.

## Accessibility & Inclusion
WCAG 2.1 AA + 2.2 (axe in CI, 0 serious/critical), light and dark themes, 360 px phone width, keyboard shortcuts in SIA, 24 px minimum target size.
