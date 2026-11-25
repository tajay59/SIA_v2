---
name: SIA (CIMH Stores staff app)
description: Graphite Console. Persistent panels on graphite; colour only for state and the one primary action.
colors:
  graphite-ground: "#16191D"
  graphite-panel: "#1C2026"
  graphite-raised: "#22272E"
  seam: "#30363D"
  field-edge: "#6E7A87"
  console-ink: "#E6EDF3"
  console-ink-muted: "#9DA7B3"
  action-blue: "#5CC2FF"
  on-action: "#0D1117"
  action-subtle: "#0B2A3D"
  done-green: "#3FB950"
  verify-amber: "#F2B13A"
  expiring-red: "#F97066"
  graphite-ground-light: "#F6F8FA"
  graphite-panel-light: "#FFFFFF"
  graphite-raised-light: "#EEF1F4"
  seam-light: "#D0D7DE"
  field-edge-light: "#7F8B98"
  console-ink-light: "#14191F"
  console-ink-muted-light: "#57606A"
  action-blue-light: "#006FA8"
  on-action-light: "#FFFFFF"
  action-subtle-light: "#E6F4FB"
  done-green-light: "#1A7F37"
  verify-amber-light: "#B54708"
  expiring-red-light: "#B42318"
  logo-blue: "#0084C8"
  probono-yellow: "#F5C400"
  probono-ink: "#1A1A1A"
typography:
  page-title:
    fontFamily: "Inter Variable, Inter, system-ui, sans-serif"
    fontSize: "28px"
    fontWeight: 600
    lineHeight: "36px"
    letterSpacing: "-0.3px"
  section-title:
    fontFamily: "Inter Variable, Inter, system-ui, sans-serif"
    fontSize: "18px"
    fontWeight: 600
    lineHeight: "26px"
  identity:
    fontFamily: "Inter Variable, Inter, system-ui, sans-serif"
    fontSize: "20px"
    fontWeight: 600
    lineHeight: "26px"
    letterSpacing: "-0.01em"
  next-step:
    fontFamily: "Inter Variable, Inter, system-ui, sans-serif"
    fontSize: "16px"
    fontWeight: 600
    lineHeight: "22px"
  body:
    fontFamily: "Inter Variable, Inter, system-ui, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: "20px"
    fontFeature: "\"cv11\", \"ss01\""
  label:
    fontFamily: "Inter Variable, Inter, system-ui, sans-serif"
    fontSize: "13px"
    fontWeight: 500
    lineHeight: "18px"
    letterSpacing: "0.1px"
  button:
    fontFamily: "Inter Variable, Inter, system-ui, sans-serif"
    fontSize: "14px"
    fontWeight: 500
    lineHeight: "20px"
    letterSpacing: "0.00625em"
  caption:
    fontFamily: "Inter Variable, Inter, system-ui, sans-serif"
    fontSize: "12px"
    fontWeight: 400
    lineHeight: "16px"
    letterSpacing: "0.1px"
  panel-title:
    fontFamily: "Inter Variable, Inter, system-ui, sans-serif"
    fontSize: "11px"
    fontWeight: 600
    lineHeight: "16px"
    letterSpacing: "0.08em"
  mono:
    fontFamily: "JetBrains Mono, ui-monospace, monospace"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: "20px"
rounded:
  control: "2px"
  badge: "3px"
  seam: "4px"
  chip: "8px"
  pill: "999px"
spacing:
  sp-1: "4px"
  sp-2: "8px"
  sp-3: "12px"
  sp-4: "16px"
  sp-6: "24px"
  sp-8: "32px"
  sp-12: "48px"
components:
  button-primary:
    backgroundColor: "{colors.action-blue}"
    textColor: "{colors.on-action}"
    typography: "{typography.button}"
    rounded: "{rounded.pill}"
    padding: "0 24px"
    height: "40px"
  button-outlined:
    backgroundColor: "transparent"
    textColor: "{colors.action-blue}"
    typography: "{typography.button}"
    rounded: "{rounded.pill}"
    padding: "0 24px"
    height: "40px"
  button-danger:
    backgroundColor: "transparent"
    textColor: "{colors.expiring-red}"
    typography: "{typography.button}"
    rounded: "{rounded.pill}"
    padding: "0 24px"
    height: "40px"
  panel:
    backgroundColor: "{colors.graphite-panel}"
    rounded: "{rounded.seam}"
  panel-head:
    textColor: "{colors.console-ink-muted}"
    typography: "{typography.panel-title}"
    padding: "0 16px"
    height: "44px"
  queue-row:
    textColor: "{colors.console-ink}"
    typography: "{typography.body}"
    padding: "0 16px"
    height: "44px"
  queue-row-hover:
    backgroundColor: "{colors.graphite-raised}"
  queue-row-selected:
    backgroundColor: "{colors.action-subtle}"
  nav-item:
    textColor: "{colors.console-ink}"
    typography: "{typography.body}"
    padding: "0 16px"
    height: "32px"
  nav-item-active:
    backgroundColor: "{colors.graphite-raised}"
    textColor: "{colors.console-ink}"
  stage-tab:
    textColor: "{colors.console-ink-muted}"
    typography: "{typography.label}"
    padding: "0 16px"
    height: "44px"
  stage-tab-active:
    backgroundColor: "{colors.action-subtle}"
    textColor: "{colors.console-ink}"
  status-chip:
    typography: "{typography.label}"
    rounded: "{rounded.chip}"
    padding: "0 12px 0 8px"
    height: "28px"
  probono-badge:
    backgroundColor: "{colors.probono-yellow}"
    textColor: "{colors.probono-ink}"
    rounded: "{rounded.badge}"
    padding: "1px 6px"
  scan-field:
    backgroundColor: "{colors.graphite-panel}"
    textColor: "{colors.console-ink}"
    typography: "{typography.mono}"
    rounded: "{rounded.control}"
  next-step-well:
    backgroundColor: "{colors.graphite-raised}"
    rounded: "{rounded.seam}"
    padding: "12px 16px 16px"
---

# Design System: SIA (CIMH Stores staff app)

Scope: the staff app in `web/sia`, as built on 2026-11-12. Tokens come from `packages/web-ui/src/theme.ts` (`siaDark` / `siaLight`, which keep the theme names `cimhDark` / `cimhLight`), `packages/web-app/src/styles/base.css`, `web/sia/src/console.css` and the shell and request components. SHOP keeps the older `cimhLight` / `cimhDark` palette from `docs/DESIGN_BRIEF.md`; this file does not describe SHOP.

## Overview

**Creative North Star: "Graphite Console"**

SIA is a working console, not a website. Panels sit on a graphite ground and stay put: the drawer, the work queue and the selected item's detail share the window, and navigating changes what the panels hold instead of replacing the page. Panels are cut apart by 1 px seams, not floated on shadows. Dark is the default (`storedTheme('cimhDark')`); the light theme mirrors it with white panels and pale seams.

Colour is reserved. Action blue marks the one primary action, the selected row and the active place; amber, red and green mean state (verify, expiring or failed, done) and always travel with an icon and a word. Everything else is ink, muted ink and seams. Type is compact Inter at 13 to 14 px for rows and controls; codes, counts and ids are set in JetBrains Mono with tabular figures. Panels name themselves with a small uppercase header.

Motion is quiet and functional: counts roll when they change, rows enter, leave and re-sort in place, the detail panel swaps in from the queue's side, and a View Transition morphs the request pane when it opens beside the queue or moves to its own page. Every motion has a reduced-motion path.

**Key Characteristics:**
- Persistent panels on graphite, separated by 1 px seams, 4 px corners.
- Colour only for state and the primary action; state is never colour alone.
- Compact Inter for UI, JetBrains Mono for codes, ids and figures.
- Material 3 pill buttons beside square-cornered panels.
- Dark by default, light as an equal mirror.

## Colors

A graphite neutral ladder with one blue for action and three state hues; the brand blue appears only in the mark.

### Primary
- **Action Blue** (`action-blue`, light `action-blue-light`): the filled primary button, outlined and text button labels, links, the active nav icon and its 2 px edge bar, the selected-row bar, the active stage-tab underline, the collapsed-rail count dot.
- **Action Wash** (`action-subtle`, light `action-subtle-light`): background of the selected queue row, the active stage tab, the "Selected request" panel header and the section heads of a request (A-03: Request, Items, Quote, …; title in primary, 2026-11-24).

### Neutral
- **Graphite Ground** (`graphite-ground`, light `graphite-ground-light`): app background behind the panels; also the open request view inside the desk.
- **Graphite Panel** (`graphite-panel`, light `graphite-panel-light`): panels, drawer, app bar, filter bar, tab strip.
- **Graphite Raised** (`graphite-raised`, light `graphite-raised-light`): row and nav hover, the active nav row, the Next step well; in dark mode also the drawer tooltip (theme `surface-bright`, which is white in light mode).
- **Field Edge** (`field-edge`, light `field-edge-light`; theme `field-outline`, shared with SHOP): the 1 px resting edge of every input. At least 3:1 on the ground, a panel and a raised well (WCAG 1.4.11); the seam is too faint for that (about 1.5:1 on white).
- **Seam** (`seam`, light `seam-light`): every 1 px divider and panel edge, outlined-button border, neutral status chip outline, kbd hint border, scrollbar thumb. Also Vuetify's `border-color`.
- **Console Ink** (`console-ink`, light `console-ink-light`): body text and row text.
- **Muted Ink** (`console-ink-muted`, light `console-ink-muted-light`): Vuetify `secondary`; panel and group titles, nav icons, counts, waiting time, fact labels, codes in compact rows. Medium-emphasis opacity is 0.74.

### State
- **Verify Amber** (`verify-amber`, light `verify-amber-light`): work that needs staff now (agreement to verify, overdue waiting time, urgent stage tab, Awaiting agreement chip).
- **Expiring Red** (`expiring-red`, light `expiring-red-light`): quote expiring, failed or refused, the destructive outlined button.
- **Done Green** (`done-green`, light `done-green-light`): completed states, full pick lines, a successful scan.
- Info uses Action Blue (theme `info` = `primary`).

### Brand
- **Focus ring:** 2 px, offset 2 px, in the theme primary (Action Blue: #006FA8 light, #5CC2FF dark), from `base.css`.
- **Logo Blue** (`logo-blue`): brand reference only; not for text (4.09:1 on white). The SIA mark (`packages/web-app/src/assets/brand/sia-mark.svg`) carries its own artwork blues and near-black and is used as supplied.
- **Pro Bono Yellow** (`probono-yellow`, theme `accent-probono`) with **Pro Bono Ink** (`probono-ink`, CSS `--probono-ink`): the Pro Bono badge only, ink text only. One shared `.probono-badge` in `packages/web-app/src/styles/base.css` for SHOP and SIA.

### Named Rules
**The State-Only Colour Rule.** Amber, red and green appear only when something is in that state; a quiet queue is ink and seams. Stage tints and decorative colour were removed from the dashboard for this reason.

**The Never-Colour-Alone Rule.** Every state colour carries an icon and a word: status chips (icon + sentence-case word), "Overdue" and "Expiring" in queue rows, the Next step sentence.

## Typography

**Display Font:** none; SIA has no display level in use (`t-display` is unused).
**Body Font:** Inter Variable (self-hosted via `@fontsource-variable/inter`), with system-ui fallback; features `cv11`, `ss01`.
**Label/Mono Font:** JetBrains Mono 400 and 500 (self-hosted via `@fontsource/jetbrains-mono`), ui-monospace fallback.

**Character:** a compact, neutral grotesque for everything people read, and a monospace only where the content is a code, an id or a count that must line up.

### Hierarchy
- **Page title** (600, 28/36, -0.3px): the shell's `h1` above each page (`route.meta.title`).
- **Section title** (600, 18/26): `t-h3`, the most-used heading inside pages; `t-h2` (22/30) appears on a few pages.
- **Identity** (600, 20/26, -0.01em): the customer or organisation name heading the request detail.
- **Next step** (600, 16/22): the one sentence that says what to do with the selected request.
- **Body** (400, 14/20 in rows and nav; `t-body` 14/22 in running text): the default UI size.
- **Label** (500, 13/18, 0.1px): status chips, stage tabs, field labels.
- **Button** (500, 14/20, 0.00625em, no uppercase).
- **Caption** (400, 12/16): fact labels, hints, secondary lines.
- **Panel title** (600, 11/16, 0.08em, uppercase, muted ink): the heading of a panel or drawer group.
- **Mono** (400, 13/20; 12/16 for full ids and counts): request ids, unit and shelf codes, counts, the scan field's input, kbd hints. Always with tabular figures.

### Named Rules
**The Codes-in-Mono Rule.** A value someone could scan, type or compare (ids, barcodes, counts) is set in JetBrains Mono with `tabular-nums`; prose and names never are.

**The Panel-Names-Itself Rule.** A panel's heading is its own small uppercase header in the 44 px head bar; it is the heading, not a label above another heading.

## Layout

- **Shell:** a left navigation drawer (240 px; collapses to a 64 px icon rail, remembered per device) is permanent at 1280 px and wider. Below 1280 px a 56 px app bar opens it as a temporary drawer. There is no top navigation bar.
- **Console panels:** queue and detail sit side by side in one bordered frame (`3fr` queue, `2fr` detail, detail at least 320 px). At 1280 px and wider the page fits the window and only the panels' bodies scroll. Below 1280 px they stack; below 600 px the detail panel is hidden (rows open the request page).
- **Request open beside the desk:** the queue narrows to 280 to 340 px and the request fills the rest; below 900 px the request takes the full width.
- **Content width:** the request desk caps at 1500 px, the page title block at 1440 px.
- **Spacing:** a 4 px grid exposed as `--sp-1` to `--sp-12` (4, 8, 12, 16, 24, 32, 48). Panel heads and rows use 16 px side padding; gaps inside toolbars and rows are 8 to 12 px; page padding is 16 to 24 px.
- **Density:** Vuetify `compact` globally (SIA), rows 44 px, nav rows 32 px (40 px in the rail).
- **Breakpoints:** 600 px (phone), 900 px (open request takes the width), 1280 px (permanent drawer, side-by-side panels).

## Elevation & Depth

Flat by default. Depth comes from the tonal ladder (ground, panel, raised) and 1 px seams, not from shadows. Shadows exist only for transient lift and floating overlays: a level-1 shadow under a filled pill button on hover, a soft shadow under the drawer tooltip, and Vuetify's own elevation on menus, dialogs and snackbars. Inset 2 px bars mark selection and place; they are indicators, not elevation.

### Shadow Vocabulary
- **Button hover** (`box-shadow: 0 1px 2px rgba(0,0,0,0.3), 0 1px 3px 1px rgba(0,0,0,0.15)`): filled M3 buttons on hover only; outlined and text buttons never lift.
- **Floating tooltip** (`box-shadow: 0 6px 18px rgba(0,0,0,0.28)`): the drawer's title + description tooltip.
- **Sign-in picture** (`box-shadow: 0 24px 48px -28px rgba(8,20,32,0.45)`): the framed picture on the sign-in pages only (outside the console; dropped on phones).

### Named Rules
**The Seams-Not-Shadows Rule.** Panels at rest have no shadow; they are separated by a 1 px seam and a step on the tonal ladder. Shadow belongs to hover lift and floating overlays.

## Shapes

Square-ish containers, round controls. Panels, the stage-tab strip, the filter bar, the Next step well, tooltips and skeleton blocks use 4 px corners; the Pro Bono badge and kbd hints 3 px; status chips 8 px; console buttons and the filter count badge are full pills (999 px). Nav rows are square (`rounded="0"`). Vuetify defaults for SIA set buttons, cards and fields to `rounded: 'sm'`, which Vuetify 4 resolves to 2 px (built CSS `.rounded-sm`), not the 4 px `r-sm` of `tokens.ts`; buttons without the `m3` class keep that 2 px corner (none left on the sign-in pages, the 404 or the profile since 2026-11-14).

## Components

### Buttons
Material 3 pills, calm until touched.
- **Shape:** full pill (999 px), 40 px tall, 24 px side padding (16 px leading when there is an icon, 8 px icon gap).
- **Primary:** filled Action Blue with `on-action` label; the detail panel shows the filled action for the request's current step (from its allowed actions), with secondary actions outlined.
- **Hover / Focus:** state layer at 8% on hover and 12% on press or focus; filled buttons gain the level-1 shadow on hover (200 ms, `cubic-bezier(0.2, 0, 0, 1)`).
- **Outlined:** 1 px seam outline, Action Blue label, no lift.
- **Danger:** outlined with a 50% red outline and red label; placed alone, away from the primary action (detail footer: the way out on the left, Reject on the right). Class `m3-danger` on an outlined or text `m3` button; its selector must out-rank the outlined/text rules in `console.css` (it did not until 2026-11-18, so danger buttons drew blue).
- **Text links in panels:** Action Blue, 600, underline on hover with the trailing arrow nudging 3 px.

### Timelines (2026-11-24)
Every timeline is a Vuetify `v-timeline` (`side="end"`, compact, `truncate-line="both"`; `role="list"` / `listitem`, since its items are divs).
- **Request timeline (A-03, web-app `RequestTimeline`):** horizontal when the panel gives each step 132 px, vertical otherwise. 22 px dots: done = success with a tick, current = Action Blue with a 4 px 24% ring, closed = error with a cross, not reached = 2 px hollow ring in `on-surface-variant`. Line success up to the current step, else a solid 20% ink mix. Label 600, date/time under it.
- **Account status history (A-17):** vertical, newest first; 12 px node (latest filled Action Blue, earlier hollow), seam line, status chip + actor + reason, mono date under.
- Lines are solid colours: Vuetify's segments overlap between items, so a translucent line shows darker dashes.

### Switches and dialogs
- **Switch off:** outlined track (2 px `field-outline`) with an outline-coloured thumb, as Material 3 draws it; on keeps the filled primary track. Vuetify's default off state vanished on white panels.
- **Dialog titles** wrap instead of being cut to one line.
- **Narrow tables** (request Items): below 520 px of panel width each row becomes a block of label / value pairs.

### Chips
Status, never an action.
- **Style:** 28 px tall, 8 px corners, 18 px filled icon, label 13/500. Tonal fill at 8% of the tone, 1 px outline at 32%, label = tone mixed 72% toward ink (AA on the tint); icon keeps the pure hue.
- **Neutral:** outline only (seam), ink label, muted icon, so "nothing to do yet" reads quieter than states that need attention.
- **Mapping:** one table for every app (`packages/web-ui/src/status.ts`): neutral, info, warning, success, error.

### Cards / Containers (console panels)
- **Corner Style:** 4 px on the outer frame.
- **Background:** Graphite Panel.
- **Shadow Strategy:** none (see Elevation & Depth).
- **Border:** 1 px seam around the frame and between panels.
- **Head:** 44 px bar, 16 px side padding, seam underneath, panel title left and controls right. The detail panel's head is washed in Action Wash with a blue title.
- **Internal Padding:** 16 px; 20 px gaps between detail sections.

### Inputs / Fields
- **Style:** every Vuetify input (text field, select, autocomplete, combobox, textarea, file, number, OTP) is `solo-inverted` and flat (owner, 2026-11-12; set once in `packages/web-ui/src/theme.ts` defaults), compact density, pill-shaped (owner, 2026-11-20; was 2 px corners; textareas 24 px). A field that must be the page's main target (Pick Order's Unit) adds a 2 px primary ring (`ScanField prominent`).
- **Edge:** a solo-inverted field at rest has the colour of the panel it sits on, so every field carries a 1 px Field Edge (`base.css`, a `::after` on `.v-field`, because Vuetify's hover/focus overlay paints over the field's own box). Error: the edge turns red.
- **Focus:** the edge becomes 2 px Action Blue on the raised fill; the global focus ring is suppressed inside fields.
- **6-digit codes:** always six OTP boxes (`v-otp-input`: verify email, MFA, password reset), never a text field.
- **Scan field:** a form around a solo-inverted field with a barcode icon, mono input text, a persistent hint and a tonal "Enter" button inside. Enter submits one scan, the field clears and keeps focus.
- **Terms row** (quote builder, 2026-11-18): when fields sit side by side in a strip and their names are long, the name goes **above** the field as a caption (label 13/18 500, muted ink, a real `<label for>`) and the field has no inner label, so nothing is cut off. Each cell is caption, 40 px solo-inverted field, one reserved 12/16 message line (a hint in muted ink, or an error in red with a 14 px icon), so the row never jumps. A wrong value is marked at once; a missing one only after the action that needs it (Preview, Send) was pressed. Units travel as prefix/suffix ("1 USD = … BBD", "USD") in mono and stay visible at rest (`persistent-placeholder`); the placeholder is then a word in muted ink ("rate", "amount"), never a number that reads as a value. Cells keep fixed widths and wrap whole; a destructive action at the end of the row turns icon-only (aria-label + title) when the row is short of room (container query), and keeps its word on phones.
- **Segmented choice** (2 to 6 options that switch a form, e.g. a currency or a keep-for period; `scroll` keeps one row that scrolls sideways in narrow panes instead of wrapping): Material 3 segmented button built from native radios (arrow keys for free): 40 px tall to match the fields, full-pill outer edge in Field Edge, segments split by 1 px, the chosen one on Action Wash with weight 600 and an 18 px Action Blue check; focus = 2 px primary ring inset. Not `v-btn-toggle`, whose pills fall apart in the M3 button styles.

### Sign-in pages (`AuthCard`, shared with SHOP)
Category-standard split sign-in (owner, 2026-11-16; brief `packages/web-app/.impeccable/surfaces/src-components-authcard-vue.md`). Used by log in, sign up, verify, forgot/reset password, MFA setup and staff-only.
- **Picture side (left half, sticky, full height):** the picture sits in a frame inset 16 px on the form-side ground, 12 px corners, one soft shadow (`0 24px 48px -28px rgba(8,20,32,0.45)`; the only rest shadow, outside the console), `object-fit: cover`. A bottom scrim (transparent to 55%, then `rgba(8,20,32,0.72)`) carries the foot, 32 px in: the optional `wall` slot (sign-up: the steps to an approved account, white) above a caption chip (28 px pill, 12/600, `rgba(8,20,32,0.55)` + 6 px blur; "Meteorological enclosure" on the legacy stand-in photo, "Illustrative image" on a generated one). Media come from `assets/auth/sia.*` (`authMedia` in `auth-motion.ts`); a video (muted loop, poster = the still) plays only without reduced motion and gets a Pause/Play pill top right (WCAG 2.2.2).
- **Form side (right half):** always the dark ground `#0d1117` under `v-theme-provider` `cimhDark`, whatever theme is stored (ink `#e6edf3`, muted `#9aa7b4`, line `#262d36`, frame `#161b22`). One column, max 400 px (or `width` − 80, at most 460), anchored at a top offset (`clamp(16px, 5vh, 56px)`) so heading, step track and fields stay put between steps; 32 px gaps. Brand row aligned to the column: white CIMH crest (176 px) left, SIA mark + "SIA · Staff app" (13/600 muted) right. Title 32/40, 700, −0.02em, balanced; one 16/24 muted line; the form (button labels 600); footer links above a 1 px line; legal line at the foot.
- **Sign-up (`SignupForm`):** three steps (You · Details or Organisation · Password) as a track of 3 px top rules with 13/600 labels; one primary indicator slides to the current step (420 ms, transform); done steps are links back. Panes slide in the direction of travel (forward from 32 px right, Back from the left; in 280/360 ms, out 120 ms) and the pane heading takes focus.
- **Phones and tablets (< 960 px):** one column; the picture becomes a 200 px band (12 px inset, no shadow, wall hidden); crest 144 px, title 26/32; the steps list moves under the form into a `#161b22` well (12 px corners).
- **Motion (`auth-motion.ts`):** the arrival is `load` (direct load or from an app page: the picture settles from scale 1.04 + fade over 1.4 s, the column rises 12 px in 640 ms, staggered 0/80/160 ms), `vt` (between sign-in pages: one View Transition; the picture holds still as `auth-visual`, words, form and foot lift out in 160 ms and settle in over 440 ms, the form morphs to its new height) or `plain` (no View Transitions, reduced motion, or WebKit: only the column rises). Reduced motion: no entrance, no video, no pane slide or indicator glide.

### Profile (`ProfileView` + `ProfileSection`, shared with SHOP)
In SIA each section is a console panel (seam, 4 px corners, 44 px head with the panel title); dividers inside are seams; actions are outlined pills, Save the filled pill, Ask to delete the danger pill. SHOP keeps cards.

### Dialogs
- **Only Vuetify `v-dialog`** for every modal in SHOP and SIA (owner, 2026-11-12): no native `<dialog>`, `window.confirm/alert/prompt` or hand-made overlays.
- Theme defaults (`packages/web-ui/src/theme.ts`, `VDialog` nested defaults): the card inside a dialog is elevated on `surface` (cards elsewhere stay outlined and transparent), and fields inside a dialog take `surface-variant` so they stay visible on the card.
- **Confirms** (2026-11-15): an action that can't be undone, or that emails someone, asks first: the dialog names the record and says what happens; the safe button says what it keeps ("Keep editing", "Keep issued"), the acting button repeats the verb ("Email the customer", "Return unit"). Red only for the irreversible ones (Erase, Merge, Remove).
- **Submit, then mark:** submit pills are never disabled for missing input; pressing one runs `checkForm` (web-app `form.ts`), which marks every field and focuses the first. Disabled is kept for "nothing changed" (the save bar says "All changes saved") and while saving. Exception: small dialogs whose one field carries the hint (reason dialogs; Erase, where typing the email is the safeguard).
- Anatomy: title + subtitle (the record's mono id and name), seam dividers, body, actions right-aligned (Back text, primary filled pill). A confirm that sends a document shows the document: the quote builder's review dialog (1240 px) puts the agreement PDF, exactly as the customer gets it and marked as a preview, on the left and the summary on the right (phones: fullscreen, summary first). Choices of 2-4 options are radio tiles (icon + radio + word), e.g. the carriers in Record shipment (`ShipmentDialog.vue`, icon over word, one row of five, wrapping and stretching on phones). **Every dialog follows one golden-ratio system** (owner 2026-11-24; defaults in web-app `base.css` (shared with SHOP), so a plain `v-card-title`/`-text`/`-actions` dialog gets it without code): type 11 px uppercase captions (14/√φ) · 14 px body and fields · 17.8 px section heads (14·√φ) · 22.65 px title and key figure (14·φ); spacing Fibonacci 8 · 13 · 21 · 34 (21 px edge, 13 on phones); fields with 8 px corners (not pills); a checkbox, radio or switch 13 px from its words; plain surface heads, never a washed band. Task dialogs that change a request (Verify and purchase, Record shipment) share one anatomy: a plain head split φ : 1 (title, who and the full order id with copy, muted; one key fact right: Agreed total / Ships to) over a hairline, numbered steps with no box and no wash (a 17.8 px section head with its state on the right, 13 px to the content, 34 px and a hairline before the next step), a purchase-order table without rules (From φ : PO number 1), and a footer with the consequence beside Back + the primary action. Larger dialogs (invoice builder) keep the title's 24 px edge for every part; no bordered box inside a dialog except a document reader and choice/file rows. **Invoice builder panel** (owner 2026-11-24): its own golden-ratio system: three sizes (11 px uppercase captions = 14/√φ, 14 px body and fields, 22.65 px total = 14·φ), Fibonacci spacing 8 · 13 · 21 · 34 (8 in a group, 34 between sections), preview √φ : panel 1 (panel ≥ 520 px), number φ : date 1, totals ledger 61.8 % of the panel set right. Its fields are the one exception to the pill rule: 8 px corners, and 32 px high with a 10 px inset in the lines table and the ledger, so a row reads as a table row (the table has no rules). The email choice sits in the footer as checkboxes.
- **A record a dialog reopens** (invoice builder, 2026-11-24): one dialog, three modes. **New** (title "Create …", primary Create). **Open** (title = the record's number; a muted state line under the subtitle: "Revision n · Made automatically …"; **Earlier copies** as quiet text links that open the file preview; the saved document on the left until a field changes, then the live preview with a one-line note saying what saving does; footer: the destructive action first and apart (outlined danger pill with an icon, its own row at the left on phones), then the email ticks (unticked for a correction), Back, **Save changes**, disabled only while nothing changed). **Locked** (paid): fields read-only, no add/remove, footer Close (+ Void for an admin). Someone saved first: a warning-wash notice with Reload above the form.


### Navigation
- **Drawer:** brand mark row, groups Work / Stock / Reports / Admin with uppercase group titles, flat 32 px rows (20 px muted icon, 14 px label, mono count on the right), scan box and account/theme controls at the foot behind a seam.
- **Hover:** Graphite Raised.
- **Active:** Graphite Raised ground, label 600, blue icon, 2 px Action Blue bar on the row's right edge (`aria-current="page"`).
- **Rail:** icons only, centred; counts become a 7 px blue dot; groups separated by seams; every item has a tooltip with title, count and a one-line description.

### Stage tabs (request desk)
One connected strip cut by seams, 44 px cells, 13/500 muted labels with a mono count. Active: Action Wash, ink label 600, 2 px Action Blue underline. A stage with urgent work turns its label and count amber.

### Queue row
Grid row, 44 px, seam below: mono id (in full when its column has room), customer (500) with the Pro Bono badge at the right edge of its column, a reason line with icon + word on one line (never wraps; a long one ends in "…", whole sentence as its title), optional status chip (200 px column, only when the list is ≥ 900 px wide: the columns follow the list's width by container query, not the window's), waiting time right-aligned. The reason gets the widest share of the row. Hover: Graphite Raised. Selected: Action Wash with a 2 px Action Blue bar on the left. Overdue waiting turns amber with the word "Overdue"; expiring quotes turn red. In compact mode (beside an open request) and on phones the row becomes two lines (who + wait, why + code).

### Next step well
The one decision in the detail panel and its one coloured region (colorize 2026-11-16): when staff act, the well takes its tone (Action Blue for act/fulfil, amber urgent, red expiring) as a 12 % wash with a full 1 px edge at 55 %, the "Next step" label and icon in that hue and the sentence in ink at 18/24 700; waiting on the customer and closed stay a Graphite Raised well with a seam edge and a muted 16/600 sentence. 4 px corners; the inline actions follow as M3 buttons.

### Announcement banner (shared with SHOP)
Admin messages (A-22) above the app bar and drawer on every page: a Vuetify layout slot (`v-app-bar` order −1, measured height, `density="default"` because SIA's compact toolbars reserve 16 px less). Rows: Information = Action Blue wash 14 % with a full 1 px edge at 45 %, Alert = Verify Amber wash 22 %; icon in the hue, the word ("Information:" / "Alert:") bold in ink, text 14/20 in ink (2 lines, then More), link underlined in ink, Close (information only) as a small text icon button. SIA rows run full width beside the drawer; SHOP rows sit on SHOP's 1200 px column. Arrival slides down 180 ms, leaving fades 140 ms; reduced motion = fade. The admin preview draws the same `AnnouncementRow` on small SHOP/SIA page sketches in light and dark.

### Scan icon (2026-11-25)
Wherever SIA asks for a scan (`ScanField`, the drawer's scan box, scan actions in `request-queue.ts`, the history ledger's unit field) the icon is `src/icons/QrScan.vue`: a QR code inside scan-frame corners (owner's SVG, 48 px grid), drawn in currentColor at 1em, passed to Vuetify as a component (`markRaw`). It replaced `mdiBarcodeScan` and Material Symbols `barcode-scanner`.

### List leave motion (2026-11-25)
TransitionGroup lists whose leaving items go `position: absolute` pin them first (`@before-leave="pinLeaving"`, `src/list-motion.ts`: top, left, width, height from layout; the list is `position: relative`), so a filter or tab change fades the old rows out in place instead of stacking them on row one. Products rows leave at once instead.

### Shelf label (2026-11-25)
`LabelSheet` items with `shelf` follow the legacy printed shelf label: black on white, site (row 1, beside SHELF n) and location (row 2) 14/18 500 upper case, the full shelf code across the label in JetBrains Mono 11 px on one line, then the QR as wide as the label (no rounded corners). Labels 260–320 px on screen, 2 per printed row. Unit labels keep the compact QR + short code card.

### Pro Bono badge
11/16, 600, 0.02em, 1 px × 6 px padding, 3 px corners, Pro Bono Yellow with Pro Bono Ink. In list rows it sits at the right edge of its line (owner 2026-11-25).

### Pick rails: queue head, Purpose, shelf (2026-11-25)
Golden-ratio steps (11 / 14 / 17.8 px; 8 · 13 · 21 spacing), sides on the rows' 16 px edge, nothing wraps: title 17.8/600 in ink with the count beside it in mono, medium ink; the order ("Longest wait first") 11 px muted under it; Refresh as a text icon button with a tooltip; the request-id field below with its label for assistive tech only (`ScanField hide-label`) and the placeholder in Inter. Pick Order line cards have no border at all (the bar and n / N say a line is full). The Purpose and shelf rails share the head (`ph-head`, `ph-sub`) and body steps (13 between parts, 21 at the foot): purposes are tonal buttons in an even 2 × 2 grid (chosen = tonal primary + check), a hairline foot row holds the way out (11 px question + small tonal button); the shelf card sets "Shelf n" at 22.65 px (14 × φ) beside its tally (mono 17.8 count, 11 px "put here"), the location 14 px in ink, the site 11 px muted; Change shelf is tonal.

### Motion
- Easing `cubic-bezier(0.16, 1, 0.3, 1)` (`--ease-out`) for arrivals; `ease-in` for exits.
- Queue rows: enter 220 ms with a 24 ms stagger (fade + 6 px rise), leave 140 ms fade, re-sort 280 ms.
- Counts roll in over 320 ms; the detail body swaps in over 200 ms from 8 px to the right; skeletons shimmer over 1.4 s.
- Request pane View Transition: 320 ms group morph, 120 ms out, 240 ms in.
- Desk (summary beside the queue) → the request's own page, e.g. **Verify and purchase** (2026-11-24): a quiet hand-off, not a morph (the summary is a different view from the page). `vt-quiet` on `<html>` drops the pane/queue names; the desk (`request-desk-out`) fades out in place in 80 ms, the page (`request-page-in`) settles 4 px over 180 ms after 60 ms. Two names, so neither slides towards the other's box. The way back keeps the morph.
- `/pick`: the tab underline slides (260 ms, transform only); a tab fades in (180 ms); an opened request swaps in (220 ms); a unit landing on its line flashes the line (900 ms success wash), fills its bar (`scaleX`, 320 ms) and rolls the counts; scan results drop in (220 ms), a refusal nudges sideways once (280 ms), earlier results slide down (240 ms).
- Products: the stock meter fills to its level (`scaleX`, 520 ms) when it appears and whenever the count changes, the count rolls only on change; list rows enter (capped 24 ms stagger) and re-sort like queue rows, and leave at once (2026-11-25: leaving rows taken out of flow without a top stacked on row one); **rows ↔ photos** (impeccable animate, motion review: ship): out-in, old view out 90 ms, new in 200 ms opacity + 260 ms settle (rows 6 px rise, photos scale 0.985 from the top), each view a keyed wrapper (a TransitionGroup cannot be a Transition's child), the scroll box holds its height through the leave, meters mounted by the switch start at their level (`StockMeter still`); the view toggle is one tonal segmented pill (chosen half tonal primary); the record morphs between beside the list and its own page (View Transition `product-pane` / `product-list`, same timing as the request pane) and swaps in when another row opens; one tab ink slides (260 ms) and the pane arrives from the previous tab's side (12 px, 220 ms); photos cross-fade; photo tiles scale in and out (0.96). **More filters** (impeccable animate, 2026-11-25, motion review: ship) unfold out of the strip: a grid row `0fr → 1fr` (real height, no JS measuring) with the page gap folded in by a margin, open 300 ms ease-out, close 200 ms `cubic-bezier(0.4,0,0.2,1)`; the panel surface and its inset seam sit on the clip, so the panel's edge arrives with the fold; only the fields fade (in 150 ms after 20 ms, out 90 ms) with a −8 px settle; closed = `visibility: hidden`; reduced motion = instant. Type filters are tonal buttons (chosen = tonal primary + check, `aria-pressed`).
- New product: the list's New product button and the `/products/new` page share the View Transition name `product-new`, so the button grows into the form and the form shrinks back into it (380 ms, snapshots clipped to the box on the page ground; old fades 100 ms, new fades in 220 ms after 90 ms).
- Inventory (`/inventory`): one 2 px place marker glides through the Places tree to the open place (transform 340 ms, placed without motion the first time) while the place wash fades in; branches unfold out of their parent row (6 px + clip reveal, 220 ms; fold 120 ms); the record swaps in from the side on every place change; a unit card or QR label unrolls under its row; product counts roll; new shelf tiles and freshly made labels arrive in a capped stagger (30 / 24 ms). New product photos (`PhotoStager`) enter, leave and reorder as tiles.
- Stock levels (`/reports/stock`): low-stock rows enter, leave and re-sort like queue rows; the stock record swaps in from 8 px on each product; meters fill (StockMeter) and shelf bars fill by count (`scaleX`).
- Movement history (`/reports/history`): rows arrive with a capped 24 ms stagger (fade + 6 px rise) whenever the log loads or a filter changes.
- Admin (`/admin`, `/admin/accounts`, `/admin/approvals`): account rows enter, leave and re-sort like queue rows; the account record swaps in from 8 px; a decided approval row leaves sideways (12 px); "Review all" / tool arrows nudge 3 px on hover.
- Admin round 2 (`/admin/organisations`, `/admin/audit`, `/admin/settings`): organisation rows like account rows, record swaps in from 8 px; audit entries arrive with the capped 24 ms stagger; a settings section swaps in from 8 px (out 100 ms), fee and project rows enter and leave 4 px.
- Admin motion pass (2026-11-13). Focal moment = **a decision landing on an account**: the new status chip or role arrives with a short Action Blue ring (scale 0.9 → 1, 420 ms), the Next step well hands over (old lifts 6 px away in 140 ms, the next settles in after 80 ms), and the new status-history entry drops in on a fading Action Wash (900 ms; since 2026-11-24 the history is a Vuetify `v-timeline` whose items are `display: contents`, so the body and the node animate and the TransitionGroup has an explicit 900 ms duration; no move transition). Accounts list ↔ record beside it ↔ own page and organisations list ↔ record morph as View Transitions (`request-motion.ts`, names `product-list` / `product-pane`). Settings: one marker glides to the open section (300 ms; along the strip on narrow screens), the unsaved dot pops in, and the save bar (`SaveState.vue`, also in the organisation record) goes Unsaved changes → a check that draws itself + "Saved" (1.8 s) → All changes saved. Admin overview: waiting items arrive in order (30 ms stagger) and leave when handled.
- Desk More filters (`/requests`, 2026-11-20): turning a filter on wipes its check in from the left (clip-path, 220 ms; Vue `<Transition>`, so only on a change, never when the panel opens); status chips: the wash fills from the left (260 ms) and drains on off (160 ms), the check opens its own room (width 0 ↔ 18 px) so neighbours glide, off wipes the check out to the right, a press squeezes to 0.96; "Only open/closed" and Clear sweep the checks in chip order (28 ms per chip); in `SegmentedChoice` one wash slides to the chosen segment (280 ms; segments that wrap paint their own); the panel head and rows rise 6 px in a 0/40/80 ms stagger behind the expand; the summary and the More filters count roll. Reduced motion: no wipes or movement, checks and rows fade.
- Invoice builder (`InvoiceDialog`, 2026-11-20). Focal = **the paper redrawing**: while the next version renders, the page on screen stays, dims to 55 % and softens (1.5 px blur, 160 ms ease-in) and a 2 px Action Blue hairline sweeps the pane's top edge (1.1 s loop, only while drawing); the new version settles back sharp (360 ms ease-out), never a blank between versions. Lines rise in 6 px (220 ms), leave sideways 12 px (140 ms), glide on reorder (280 ms); line amounts, sub-total and total roll; the to-do list drops open (clip-path, 240 ms). Reduced motion: no blur, sweep or movement; the hairline holds still, everything fades.
- Reduced motion: transforms and staggers drop to fades or nothing; the global rule cuts every duration to 0.01 ms.

## Do's and Don'ts

### Do:
- **Do** separate panels with a 1 px seam and a step on the tonal ladder (ground, panel, raised).
- **Do** keep the queue and the selected item's detail on screen together at 1280 px and wider.
- **Do** give every state colour an icon and a word, using the shared status mapping.
- **Do** make the current step's action the filled Action Blue pill and keep the rest outlined; put a destructive action outlined in red and apart from it.
- **Do** set ids, codes and counts in JetBrains Mono with tabular figures.
- **Do** head each panel with its own 11 px uppercase title in a 44 px head bar.
- **Do** mark a selected row with Action Wash plus a 2 px Action Blue bar, and the current nav place with Graphite Raised plus the same bar.
- **Do** give every animation a reduced-motion path.

### Don't:
- **Don't** put shadows on panels at rest; shadows are for hover lift and floating overlays (tooltips, menus, dialogs).
- **Don't** use amber, red or green as decoration or as a stage tint.
- **Don't** use Logo Blue for text, or Pro Bono Yellow with anything but ink text.
- **Don't** round panels beyond 4 px or round nav rows into pills.
- **Don't** hard-code colours that exist as theme tokens; read them from the Vuetify theme.
