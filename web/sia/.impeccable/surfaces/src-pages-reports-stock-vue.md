---
primaryTarget: src/pages/reports/stock.vue
relatedTargets:
  - src/components/StockMeter.vue
  - src/components/ProductPicker.vue
mode: operate
---
# /reports/stock surface brief

## Direction contract
THESIS: A restock board, not a report table: what is running out, worst first, beside the open product's stock record. The finder opens any product here instead of leaving the page.
OWN-WORLD: Graphite Console (web/sia/DESIGN.md): seams, 44 px panel heads, mono counts, state colour only with icon + word, shared StockMeter.
STORY: Staff see how many products are low and how many have none, open the worst, see where its remaining units sit and what is held back, then create labels or open the product.
FIRST VIEWPORT: Finder; one frame: "Low stock" list (name · StockMeter · held total) beside "Stock record" (name + id, large meter + verdict sentence, Reserved / Issued / Picked, shelves grouped by site with relative bars, Create labels / Open product).
LAYOUT: ≥1280 px side by side, fits the window, panel bodies scroll, the most urgent product opens by default. Below: one column, an open record first, list after; phones hide the held column and the held hints.
MOTION: rows enter (capped 24 ms stagger), leave, re-sort; record swaps in from 8 px; meters fill (StockMeter); reduced motion = fades.
