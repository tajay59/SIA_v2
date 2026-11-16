---
primaryTarget: src/pages/reports/history.vue
relatedTargets:
  - src/components/history/HistoryLedger.vue
  - src/history.ts
  - src/components/PersonPicker.vue
mode: operate
---
# /reports/history surface brief

Owner chose design A "Day ledger" (2026-11-12) over B "Log + unit trail" and C "Filter rail + table", all three built and compared in the browser.

## Direction contract
THESIS: Movement history reads like a storeroom day book: one log grouped by day, each row a sentence (time, operation, unit, where, who). Refuses the bare five-column table with raw place codes.
OWN-WORLD: Graphite Console (web/sia/DESIGN.md): seams, 44 px sticky day heads in panel-title type, mono times/codes, operation icons from one set (`OP_ICONS`), filter chips with action wash when chosen.
FILTERS: unit code (Enter / Apply), scanned by, date presets Any time · Today · 7 days · 30 days · Custom (two DateFields), operation chips (single choice; "All"). Clear filters when any is set. Days and presets are Barbados days.
READABILITY: places resolved to "Site › Location › Shelf n" (inventory /shelves, cached per page load); unit codes shortened to TYPE…last6_suffix with the full code as title.
LAYOUT: ≥900 px a table per day; below, each row is a 3-line card (time · operation · who / unit / where); phones scroll the operation chips sideways.
MOTION: rows arrive with a capped 24 ms stagger; reduced motion = fade.
