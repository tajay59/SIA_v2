# Design Brief: CIMH Stores Platform v2

| | |
|---|---|
| **Document status** | DRAFT |
| **Document owner** | T. Edwards |
| **Related documents** | [PRD](PRD.md) · [APD](APD.md) (screens) · [TRD](TRD.md) (stack) · [Manual](manual/index.html) |
| **Last updated** | 2026-11-06 |

---

## 1. Overview

Defines the **visual design direction** for SHOP, SIA and SIA Mobile: colours, fonts, spacing, components and how each screen should look, so the experience is consistent and on-brand. Tokens here map directly to the **Vuetify 4** theme (web) and **Material 3** theme (Android).

**Brand basis:**
- The **CIMH logo blue** (`#0084C8`, sampled from `cimh-logo-blue.png`).
- The **CIMH yellow** from the full-colour logo.
- Near-black ink.

The platform should feel like a **trustworthy scientific institution's service**: calm, precise, clear about status. It shouldn't feel like a flashy online shop.

**Design references** (principles only; no identity copied; via the `design-md-library` skill):

| App | Reference | What we take | What we don't |
|---|---|---|---|
| **SHOP** | Stripe | Restrained single-accent CTAs; deep-navy ink, never pure black; hairline borders; **tabular figures for money**; calm, generous white space | Gradient mesh, indigo, pill buttons, thin 300-weight display |
| **SIA** | Linear | Dense, efficient lists; surface "ladder" for depth in dark mode instead of heavy shadows; 4px spacing grid; mono for ids; one accent used sparingly | Black marketing canvas, lavender, aggressive negative tracking |

**Character in three words:** *Clear · Precise · Calm.*

## 2. Design principles

1. **Status first.** Every request, account and unit shows its status as a coloured chip with a word. Colour is never the only signal.
2. **One accent per view.** The CIMH blue marks the single primary action on a screen. Everything else is neutral.
3. **Real things, no decoration.** Product photos, real documents, real data. No stock illustrations or gradients. The single exception is the generated home-page hero image (§7).
4. **Dense where staff work, airy where customers browse.** SIA uses compact density; SHOP uses comfortable density.
5. **Numbers line up.** Money, quantities and ids use tabular figures, and ids and barcodes use mono.
6. **Accessible by default.** WCAG 2.1 AA in both themes, with visible focus, 44 px touch targets and nothing that depends on colour alone.
7. **Same system, three apps.** SHOP, SIA and Mobile share tokens and components (`packages/web-ui`) and differ only in density and navigation.

## 3. Colour

All text and component pairs below were **contrast-checked** (WCAG ratio in brackets).

### 3.1 Brand

| Token | Light | Dark | Use |
|---|---|---|---|
| `brand-logo` | `#0084C8` | `#0084C8` | Logo, focus ring, large accents, charts. **Not for normal-size text on white** (4.09:1 fails AA) |
| `primary` | `#006FA8` (white text 5.47) | `#5CC2FF` (on bg 9.57) | Filled primary button, links, active nav, selected states |
| `primary-hover` | `#00639A` (6.46) | `#7FCBF5` (10.6) | Hover |
| `primary-press` | `#005A8C` (7.39) | `#A9DCF8` | Pressed |
| `primary-subtle` | `#E6F4FB` (primary text on it 5.75) | `#0B2A3D` | Selected row, info banner, soft tags |
| `on-primary` | `#FFFFFF` | `#0D1117` | Text on primary |
| `accent-probono` | `#F5C400` | `#F5C400` | **Pro Bono** badge background; **always with ink text** (10.71) |

### 3.2 Neutrals

| Token | Light | Dark | Use |
|---|---|---|---|
| `bg` | `#F5F7FA` | `#0D1117` | Page background |
| `surface` | `#FFFFFF` | `#161B22` | Cards, tables, dialogs (surface level 1) |
| `surface-2` | `#F0F3F7` | `#1C232C` | Table header, hovered row, nested panel |
| `surface-3` | `#E6EBF1` | `#242C36` | Menus, popovers (dark-mode lift instead of shadow) |
| `hairline` | `#E1E6EC` | `#2A323C` | 1 px borders and dividers |
| `hairline-strong` | `#C7D0DA` | `#3A4552` | Input borders, emphasised dividers |
| `ink` | `#0F1A24` (17.6) | `#E6EDF3` (16.0) | Headings and body. Never pure black |
| `ink-muted` | `#53606C` (6.45) | `#9AA7B4` (7.71) | Secondary text, labels, captions |
| `ink-disabled` | `#8C97A3` | `#5C6773` | Disabled text (exempt from contrast) |
| `scrim` | `rgba(15,26,36,.48)` | `rgba(0,0,0,.6)` | Dialog backdrop |

### 3.3 Semantic

| Token | Light (on white) | Dark (on bg) | Subtle background L / D |
|---|---|---|---|
| `success` | `#1A7F37` (5.08) | `#3FB950` (7.45) | `#E8F5EC` / `#0F2A18` |
| `warning` | `#B54708` (5.43) | `#F2B13A` (10.0) | `#FDF1E7` / `#2E2209` |
| `error` | `#B42318` (6.57) | `#F97066` (6.79) | `#FDECEA` / `#2D1214` |
| `info` | = `primary` | = `primary` | = `primary-subtle` |

### 3.4 Status chip colours (one mapping, used everywhere)

| Tone | Request statuses | Account statuses | Unit states |
|---|---|---|---|
| **Neutral** (grey) | `CART`, `SUBMITTED` | `PENDING_VERIFICATION` | stowed (available) |
| **Info** (blue) | `QUOTING`, `QUOTED`, `APPROVED`, `PURCHASING`, `PICKING`, `SHIPPED` | — | reserved |
| **Warning** (amber), *needs action* | `AWAITING_AGREEMENT` | `PENDING_APPROVAL` | assigned |
| **Success** (green) | `ACCEPTED`, `DELIVERED` | `ACTIVE` | picked |
| **Error** (red) | `DECLINED`, `REJECTED`, `CANCELLED` | `REJECTED`, `SUSPENDED`, `EXPIRED` | — |

Chips have a subtle background, a toned 1 px border, toned text, an **icon**, and the **status word** in sentence case ("Awaiting agreement"). The **action-needed** state for the current user (e.g. a quote to accept) adds a small filled dot.

## 4. Typography

**Families** (open-source, **self-hosted** via `@fontsource`, no external CDN):
- **Inter** (variable) for all UI text. Turn on `font-feature-settings: "cv11", "ss01"` for clearer digits and letters, and `"tnum"` wherever there are numbers.
- **JetBrains Mono** for ids (`ORD…`), barcodes, serials, codes and exchange rates.

Android uses the same families, bundled as resources.

| Token | Size / line | Weight | Tracking | Use |
|---|---|---|---|---|
| `display` | 36 / 44 | 600 | -0.5px | SHOP home hero only |
| `h1` | 28 / 36 | 600 | -0.3px | Page titles |
| `h2` | 22 / 30 | 600 | -0.2px | Section titles, request id header |
| `h3` | 18 / 26 | 600 | 0 | Card titles, dialog titles |
| `body-lg` | 16 / 24 | 400 | 0 | SHOP body |
| `body` | 14 / 22 | 400 | 0 | **Default UI** (SIA tables, forms) |
| `body-strong` | 14 / 22 | 600 | 0 | Emphasis, table key column |
| `label` | 13 / 18 | 500 | 0.1px | Form labels, chip text, tabs |
| `caption` | 12 / 16 | 400 | 0.1px | Helper text, timestamps, meta |
| `overline` | 11 / 16 | 600 | 0.6px, UPPERCASE | Section eyebrows (sparingly) |
| `mono` | 13 / 20 | 400 | 0 | Ids, barcodes, serials |
| `money` | inherits | 500 | 0 | `tnum`; always with currency code: `BBD 1,250.00` |

Rules:
- Use sentence case everywhere, no Title Case.
- Keep line length at most 72 characters for prose.
- Never go below 12 px.
- Don't put text in images.

## 5. Spacing, layout and density

- **Base unit 4 px.** Tokens: `1`=4, `2`=8, `3`=12, `4`=16, `5`=20, `6`=24, `8`=32, `10`=40, `12`=48, `16`=64.
- **Density:**
  - SHOP: Vuetify `default` (comfortable; inputs 48 px).
  - SIA: `compact` (inputs 40 px; table rows 40 px).
  - Mobile: comfortable, with big scan targets.

**Containers:**

| | SHOP | SIA |
|---|---|---|
| Content max width | 1200 px, centred | Fluid; side nav 248 px (collapsible to 64 px) |
| Page padding | 24 px desktop / 16 px mobile | 24 px |
| Grid | 12 columns, 24 px gutter; product grid 4 → 3 → 2 → 1 | Tables full width; detail pages two columns (main 2/3, side 1/3) |
| Section gap | 48–64 px | 24 px |

**Breakpoints** (Vuetify): xs < 600 · sm 600–959 · md 960–1279 · lg 1280–1919 · xl ≥ 1920. Both web apps must work at 360 px width with no horizontal page scroll. Wide tables scroll inside their own card.

## 6. Shape and elevation

| Radius token | Value | Use |
|---|---|---|
| `r-sm` | 4 px | Chips, badges, table row highlights |
| `r-md` | 8 px | **Buttons**, inputs, menus, toasts |
| `r-lg` | 12 px | Cards, dialogs, image frames |
| `r-full` | 9999 px | Avatars and the Pro Bono badge only |

| Level | Light | Dark | Use |
|---|---|---|---|
| 0 | Flat, hairline border | Flat, hairline border | Cards and tables at rest (**default**) |
| 1 | `0 1px 2px rgba(15,26,36,.06), 0 1px 3px rgba(15,26,36,.08)` | `surface-2` + hairline | Hovered clickable card, sticky header |
| 2 | `0 8px 24px rgba(15,26,36,.12)` | `surface-3` + hairline-strong | Menus, popovers, toasts |
| 3 | `0 16px 48px rgba(15,26,36,.18)` + scrim | `surface-3` + scrim | Dialogs |

In dark mode, depth comes from the **surface ladder**, not shadows.

**Focus ring:** `2px solid brand-logo` with a 2 px offset, on every interactive element, in both themes.

## 7. Iconography and imagery

| Item | Rule |
|---|---|
| Icons | **Material Design Icons** (`@mdi/js`, tree-shaken SVG), 20 px in SIA and 24 px in SHOP, `currentColor`. Icon-only buttons need an `aria-label` and a tooltip |
| Status icons | Neutral `mdi-circle-outline` · Info `mdi-progress-clock` · Needs action `mdi-alert-circle-outline` · Success `mdi-check-circle-outline` · Error `mdi-close-circle-outline` |
| Product photos | Real photos only. Background removed by media-worker onto **white** (`#FFFFFF`, also in dark mode inside the `r-lg` frame), **4:3**, object centred with 8% padding, WebP at 320/800/full sizes. No photo → neutral placeholder with an `mdi-package-variant` icon, never a stock image |
| Hero image (S-01 only) | Generated with **OpenArt.ai**. Subject: meteorological and hydrological instruments in a Caribbean setting (e.g. an automatic weather station or radar dome under a clear sky). Style: realistic photo, natural light, calm, CIMH blues; no text, logos, people's faces or recognisable brands. Rules: no other new generated images (the legacy carousel images, radar and AWS, are reused under the legacy-structure rule; see `packages/web-app/src/assets/legacy/SOURCE.md`); it must not show or imply a specific product from the catalogue; check OpenArt's licence allows commercial use and keep the prompt, date and licence note in `assets/hero/SOURCE.md`; export WebP at 1600/800 widths, under 200 KB; alt text describes the scene |
| Logo | CIMH logo (blue on light, white on dark), min height 28 px, clear space = logo height × 0.5. Never recoloured or stretched |
| Illustrations | None. Empty states use one large icon + text + action |

## 8. Components

All components live in `packages/web-ui` (Vue, built on Vuetify 4) with matching Compose versions on Android.

### 8.1 Buttons
| Variant | Style | Use |
|---|---|---|
| **Primary** | Filled `primary`, `on-primary` text, `r-md`, height 40 (SIA) / 44 (SHOP), label 14/600 | **One per view**: Submit request, Accept, Send quote, Ship |
| **Secondary** | Outlined, `hairline-strong` border, `ink` text | Alternatives: Cancel, Download, Change choices |
| **Tertiary** | Text-only `primary` | Inline links, "View all" |
| **Danger** | Outlined `error` (filled only inside the confirm dialog) | Decline, Reject, Cancel request, Suspend |

States: hover → `primary-hover`; press → `primary-press`; disabled → 38% opacity, no pointer. While busy, a spinner replaces the label and the button keeps its width.

### 8.2 Inputs and forms
- Outlined fields, `r-md`, `hairline-strong` border → `primary` 2 px on focus. Label above the field, never only a placeholder. Helper/error text below in `caption`; errors in `error` with an icon.
- Required fields marked "(required)" in the label, not with a bare asterisk.
- **Money input**: currency code prefix, `tnum`, right-aligned. **Exchange rate**: mono, with a "BBD per 1 USD" suffix.
- **Scan input** (SIA/Mobile): large, autofocused, mono, with a barcode icon. It clears after each scan, and the result chip appears beside it.
- **File upload**: dashed `hairline-strong` drop zone, `r-lg`; shows the accepted types and the 20 MB limit; one progress bar per file.

### 8.3 Cards, lists and tables
- **Card**: `surface`, hairline border, `r-lg`, padding 24 (SHOP) / 16 (SIA). The header row holds the title (`h3`) and actions on the right.
- **Product card (SHOP)**: 4:3 white image frame → name (`body-strong`, 2 lines max) → make · model (`caption`, muted) → availability chip ("In stock" success / "On request" neutral) → Pro Bono badge if any. Hover: level 1 and the image zooms to 1.02. **No price.**
- **Table (SIA)**: header in `surface-2`, `label` weight 600; rows 40 px with hairline dividers; zebra striping off; hover `surface-2`; selected `primary-subtle`. Numbers right-aligned with `tnum`, ids in mono. A sticky header and a "load more" footer (cursor paging).
- **Queue row (A-02)**: id (mono) · customer + organisation · type badge · status chip · **waiting days** (amber after 3 days, red after 7) · quote expiry.

### 8.4 Status, badges and feedback
| Component | Spec |
|---|---|
| Status chip | §3.4; height 24, `r-sm`, icon 16 + `label` text |
| Pro Bono badge | `accent-probono` fill, `ink` text, `r-full`, label "Pro Bono", `mdi-hand-heart-outline` icon |
| Type badge | `PAID` → neutral outline "Paid"; `PROBONO` → the Pro Bono badge |
| Toast | Bottom-centre (SHOP) / bottom-right (SIA), level 2, auto-hide after 5 s (errors stay until closed), max 2 stacked |
| Banner | Full-width inline, subtle semantic background + icon, for page-level states (service unavailable, quote expiring) |
| Scan result chip | ✓ success / ✗ error, 32 px, with sound and haptics on mobile; the error text says what to do next |
| Skeleton | `surface-2` blocks shaped like the content, with a shimmer (off when reduced motion is on) |
| Empty state | 48 px muted icon, `h3` title, one sentence, one primary or secondary action |

### 8.5 Signature components
| Component | Where | Spec |
|---|---|---|
| **Status timeline** | S-11, A-03 | Vertical list. Each step has a dot (status tone), the status word, date/time, the actor, and the reason if any. Current step bold; future steps hollow and muted |
| **Quote comparison** | S-11, S-12 | Table: line · qty · **CIMH stock** column · **Supplier** column. Per line, a radio in each available option (CIMH shows a "from CIMH stock" tag). Totals row sticky at the bottom with the currency code; exchange rate shown in a caption when USD |
| **Agreement stepper** | S-12 | 3-step horizontal stepper (Choose → Download and sign → Upload). The current step is expanded; completed steps show a ✓ and the chosen summary |
| **Request header** | S-11, A-03 | Id (mono, `h2`) + type badge + status chip + key dates; the primary action on the right (from `allowedActions`) |
| **Dashboard counter** | A-01 | Card with label, big number (`h1`, `tnum`) and tone border-left 4 px when attention is needed. The whole card is clickable |
| **Approval card** | A-16 | Name, email (domain highlighted), organisation text, suggested organisation match, waiting time; Approve (primary) and Deny (danger) buttons |


> **Structure rule (owner, 2026-11-07):** every screen keeps the structure of the matching legacy page (`legacy/shop/src`, `legacy/sia/src`): same layout, navigation and section order. This brief supplies the modern look (tokens, type, spacing, components). Where this brief described a different layout, the legacy structure wins.

### 8.6 Navigation
| App | Pattern |
|---|---|
| SHOP | **Legacy SHOP structure** (TopAppBar, BottomNavBar, Footer): desktop top bar (72 px): logo left · Catalogue · Pro Bono · My requests centred (active = `primary` + underline) · theme, account menu (or Log in / Sign up) right; cart icon joins with P5. Phones: **no top bar**, a bottom navigation (Menu, Catalogue, Pro Bono, Requests; Menu holds Home, Profile, theme, Log in/out). Footer on every page (CIMH contact, stay connected + write to us, national met/hydro services, other resources). Sign-in pages have no top bar |
| SIA | **Legacy SIA structure** (AppHeader): one horizontal header (64 px): logo + "SIA" left · work areas as links (Dashboard, Products; Inventory, Pick, Stow, Orders as they ship; active = `primary` + 3 px bottom bar) · **Admin** menu (Pending accounts, Accounts, Organisations, Audit log, Settings) · theme + user menu right. Phones: a menu button opens the same links in a drawer. The page title is the page's `h1` under the header (pages with their own heading set `meta.ownHeading`). Global scan box: added to the header with P4 |
| Mobile | Material 3 bottom navigation (Home, Lookup, Stow, Pick, Orders); offline badge on Home |

## 9. Screen look (key screens)

| Screen | Layout guidance |
|---|---|
| **S-01 Home** | **Legacy Home structure**: (1) full-width hero **carousel** (440–600 px), one slide per category (owner's hero image, radar, AWS; legacy images), dark gradient on the left with title, message and a white button into the catalogue; 15 s cycle, paused on hover/focus and for reduced motion; (2) logo band on the legacy gear line-art: CIMH logo + "The Instrumentation and Equipment Spares" + "Online Stores" sign-in card; (3) "Radar Spares" and (4) "Met-service Spares": centred heading + text + a sliding row of product cards + "View all". No prices |
| **S-02 / S-04 Catalogue** | **Legacy Inventory/NCI structure**: banner with the title ("Equipment and Spares" on the gear line-art; "Pro Bono Spares" on solid `primary`) and the search box on the right; a chip row under it (types; Pro Bono: projects) with a "Filters" menu (department, project, in stock); the product grid (cards: tall 5:6 photo tile, availability chip top-right, Pro Bono badge top-left, name, make · model, "N per pack"). Search results show on the same page (`?q=`; `/search` redirects). "Load more" (cursor) instead of page numbers |
| **S-03 Product** | **Legacy InventoryItem structure**: left (3/4) a vertical thumbnail strip beside a large photo with previous/next arrows; right (1/4) one sticky card: name (`h1`), make/model, availability + Pro Bono badge with its limit, "Product description", "Details" (text + specs), "N in each pack", quantity stepper and a full-width **Add to request**. Phones: name above the photos. No price or serials |
| **S-07 / S-08 Cart → Submit** | Single column, max 720 px. Paid and Pro Bono sections separated with headings, and a note that they become two requests. Submit page: address cards (selectable), currency segmented control (BBD/USD), notes, review summary, primary "Submit request" |
| **S-11 Request (customer)** | Request header; two columns: left = quote comparison (when quoted) / lines, documents; right = status timeline + shipping/tracking card. An "action needed" banner at the top when a quote or agreement waits |
| **S-12 Choose and sign** | Agreement stepper; step 1 = quote comparison with radios + live total; step 2 = agreement card with Download (secondary) and the instruction "Sign every page"; step 3 = upload drop zone + primary **Accept and commit to pay** |
| **A-01 Dashboard** | **Legacy SIA Home structure**: statement band on the gear line-art (greeting + "The CIMH Instrumentation and Equipment Spares"), Radar / Hydro-Met spares cards into Products, "What are you looking for today?" with a product search; then counters (accounts now; requests and quotes with P5) |
| **A-05 / A-07 Products** | **Legacy SIA ProductsView / ProductPage**: list with a grid/list view toggle (remembered per device); product page = photos and a description card (serials, make/model, text) left, an "Info" card right (stock, low-stock level, cost, units per pack, department, shown to customers, id, Deactivate), then tabs Details (edit), Images, History (admins) |
| **A-02 Queue** | Filter bar (chips for status, multi-select) + table §8.3; saved filter presets: "New", "To quote", "Agreements to verify", "To ship" |
| **A-03 Request (staff)** | Request header; main column: lines table (with CIMH availability, choice and reservation columns), documents; side column: **action panel** (only allowed actions, primary first), timeline, customer and organisation card |
| **A-04 Quote builder** | Full-width table: line · qty · CIMH option (auto-priced, a toggle to offer it) · one price column per supplier (+ add supplier) with PDF upload in the column header. Sticky footer: totals per option, exchange-rate field (USD), autosave state, primary "Send quote" |
| **A-09 / A-10 / M-04 / M-07 Scanning** | One big scan input at the top, the current context (shelf/request) as a card, and a running list of results (newest on top). Success/error is shown by colour **and** icon **and** sound |
| **A-16 Approvals** | Approval cards in a single column (oldest first), a bulk-select bar sticky at the top when items are selected |

## 10. Motion

| Use | Duration / easing |
|---|---|
| Hover, focus, colour changes | 120 ms ease-out |
| Menus, toasts, expand/collapse | 180 ms `cubic-bezier(.2,0,0,1)` |
| Dialogs, drawers | 240 ms enter / 180 ms exit |
| Scan feedback | Instant colour + 150 ms scale pulse |

No parallax, no scroll-triggered reveals and no autoplaying carousels. `prefers-reduced-motion` turns off non-essential motion and shimmer.

## 11. Accessibility

- WCAG 2.1 AA: text ≥ 4.5:1, large text and UI components ≥ 3:1. Every token pair in §3 was checked.
- Status is never shown by colour alone: there is always an icon and a word.
- Keyboard: every action is reachable, focus order follows the visual order, dialogs trap focus and return it, `Esc` closes. SIA shortcuts: `/` focuses search, `g r` goes to Requests, `s` focuses the scan box.
- Touch targets ≥ 44 × 44 px (mobile ≥ 48).
- Forms: labels tied to inputs, errors announced (`aria-live="polite"`), and on submit the first error gets focus.
- Images: product photos have alt text = the product name. Decorative icons are `aria-hidden`.
- Checked in CI with axe-core and by hand with NVDA and TalkBack before release.

## 12. Voice and tone

- **Plain, polite, specific.** Write like a helpful CIMH stores officer. Avoid jargon, internal codes and exclamation marks.
- Buttons are a verb + object: "Submit request", "Download agreement", "Send quote", "Approve account".
- Status words match §3.4 exactly in every app and email.
- Errors say what happened and what to do: "This unit is reserved for request ORD…7f2. Scan a unit for this request."
- Money always carries its currency code (`USD 1,250.00`). Dates are shown as `6 Nov 2026`, times as `14:03` (Barbados).
- Use "Pro Bono" (capitalised) for free items; never "NCI" in the UI.

## 13. Email design

- Single column, 600 px max, white card on `bg`, CIMH logo header (blue), `ink` text, Inter with system fallbacks.
- One primary button (`primary` bg, white text, `r-md`) linking to the deep link in the APD §7. The full URL is also shown as text.
- Includes the status chip as a coloured text label (no images needed), the request id in mono, and the key facts (total, expiry, tracking).
- Footer: "CIMH Stores", the CIMH address (from the current templates), "You're receiving this because…". A plain-text alternative is always sent.

## 14. Implementation

### 14.1 Vuetify 4 theme (`packages/web-ui/theme.ts`)

```ts
export const cimhLight = {
  dark: false,
  colors: {
    primary: '#006FA8', 'on-primary': '#FFFFFF', secondary: '#53606C',
    background: '#F5F7FA', surface: '#FFFFFF', 'surface-bright': '#FFFFFF', 'surface-variant': '#F0F3F7',
    'on-surface': '#0F1A24', 'on-background': '#0F1A24',
    success: '#1A7F37', warning: '#B54708', error: '#B42318', info: '#006FA8',
    'brand-logo': '#0084C8', 'accent-probono': '#F5C400', 'primary-subtle': '#E6F4FB',
  },
  variables: { 'border-color': '#C7D0DA', 'border-opacity': 1, 'medium-emphasis-opacity': 0.72 },
}
export const cimhDark = {
  dark: true,
  colors: {
    primary: '#5CC2FF', 'on-primary': '#0D1117', secondary: '#9AA7B4',
    background: '#0D1117', surface: '#161B22', 'surface-bright': '#1C232C', 'surface-variant': '#1C232C',
    'on-surface': '#E6EDF3', 'on-background': '#E6EDF3',
    success: '#3FB950', warning: '#F2B13A', error: '#F97066', info: '#5CC2FF',
    'brand-logo': '#0084C8', 'accent-probono': '#F5C400', 'primary-subtle': '#0B2A3D',
  },
  variables: { 'border-color': '#3A4552', 'border-opacity': 1, 'medium-emphasis-opacity': 0.72 },
}
// defaults: VBtn { rounded: 'md', variant: 'flat' }, VTextField/VSelect { variant: 'outlined', rounded: 'md' },
// VCard { rounded: 'lg', variant: 'outlined' }, VChip { rounded: 'sm', size: 'small' }
// SHOP density 'default'; SIA density 'compact'.
```

All tokens are also exported as CSS custom properties (`--cimh-*`) for non-Vuetify CSS and the email templates.

### 14.2 Android (Material 3)
Same hex values in `Color.kt` → `lightColorScheme` / `darkColorScheme` (`primary`, `onPrimary`, `background`, `surface`, `surfaceVariant`, `error`, plus custom `success`, `warning`, `probono`). Typography: Inter, mapped to `Typography(bodyMedium = 14/22 …)`. Shapes: small 4, medium 8, large 12.

### 14.3 Do / Don't
| Do | Don't |
|---|---|
| Use `primary` for the single main action and for links | Use `brand-logo` blue for normal-size text on white |
| Show status as chip = icon + word + colour | Use colour alone, or invent new status colours |
| Use tabular figures and currency codes for money | Show prices on catalogue or product pages |
| Use real product photos on white | Use stock photos, illustrations, gradients |
| Keep SIA compact and SHOP comfortable | Mix densities within one app |
| Use the Pro Bono yellow only for the Pro Bono badge | Use yellow for warnings or with white text |
| Use one primary button per view | Use pill-shaped buttons or more than one filled button in a group |

## 15. Questions

| # | Question | Outcome |
|---|---|---|
| 1 | Is there an official CIMH brand guide? | **Resolved:** no. The colours sampled from the logo files (blue `#0084C8`, yellow) and the choices in this brief **are** the brand reference for the platform. |
| 2 | Hero image for the SHOP home page? | **Resolved:** generated with **OpenArt.ai** (see §7, "Hero image"). |
