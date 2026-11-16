---
version: 1
slug: "src-pages-inventory-index-vue"
primary_target: "src/pages/inventory/index.vue"
related_targets: ["src/components/InventoryLabels.vue","src/components/InventoryPlaces.vue","src/components/InventoryLookup.vue"]
---

# /inventory surface brief

Mode: operate. Staff on desk PCs with USB scanners and on phones in the storeroom. Jobs, equal mix: look up a shelf/unit/product, create unit labels, register sites/locations/shelves and print shelf QR codes. No constraints on structure (owner, 2026-11-12); old `?op=` links still resolve.

## Direction contract
THESIS: The storeroom itself is the page's spine: a persistent site → location → shelf tree beside whatever is open. Refuses the "choose an operation" card row and the arrows-between-forms register flow.
OWN-WORLD: SIA Graphite Console: seam-cut panels on graphite, 44 px panel heads, mono codes and counts, Action Blue only for selection and the one primary action, state chips with icon + word.
STORY: Staff scan or click a place and see what is on it; from any place they add what belongs under it (location, shelves) and print its QR codes; Create labels opens beside the tree and ends at Print / Go to Stow.
FIRST VIEWPORT: Header row: title, Register site (outlined), Create labels (filled). Prominent scan field (shelf, unit or product code, or product name). One panel: left 320 px "Places" tree (sites → locations → shelves, unit/shelf counts, + Add location / + Add shelves rows); right the open record (shelf: units list + Print shelf QR; location: shelves grid + add shelves; site: locations + add location; product: stock meter + stock by shelf; unit: unit card; labels form). Phones: tree below the record, collapsible.
FORM: Storeroom map, dealt structure 3 of 7 (surface round); seed:1ff00614d029d3be
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

## Decisions (finish review, 2026-11-12)
- The scan field and "Find a product by name" stay two fields: a scanner field must stay a plain Enter-submit input (no suggestion menu stealing keystrokes); name search needs an autocomplete.
- No mode-word head on the record; each record names itself in its own heading. Header buttons are outlined, so the open record's own submit is the one filled primary.
- No unit counts per shelf in the tree: the inventory API has no per-shelf count without paging units.
- Register site / Create labels sit in the bar under the scan field, not on the title row: the page title (h1) is rendered by the app shell (App.vue) for every page.
- Collapsed sites show no location count until opened: locations load per site on demand (there can be hundreds of sites; loading all at once jammed the browser request queue).
