---
version: 1
slug: "src-pages-products-index-vue"
primary_target: "src/pages/products/index.vue"
related_targets: ["src/pages/products/new.vue","src/pages/products/[id].vue"]
---

Scope: SIA products (A-05 list, A-06 new, A-07 product). Mode: Operate. Desk PCs (often with a USB scanner) and phones in the storeroom.
Audience/job: staff find a product (name, model, serial, barcode), check stock and where it sits, edit it, add photos, create labels; admins see cost history. Creating a product ends on its photos.
Constraints: every existing function and field stays (filters type/department/sellable/Pro Bono/inactive, grid/list toggle may go, search incl. serials, If-Match edits, drafts, deactivate, Create labels, Images panel, Stock by shelf, admin History). No facet-count API: no invented counts.

## Direction contract
FORM: List beside record (surface round, seed:c2160d71339ac65c; owner locked the second dealt structure on the decision page).
THESIS: Products works like the request desk: a list you keep, the full product record beside it.
FIRST VIEWPORT: filter strip (search, type chips, More filters), product rows (thumb, name + badges, model, stock meter) left, the full record right (header with stock meter and Create labels, tabs Overview · Edit details · Images · Stock · History).
SIGNATURE: the stock bar: available drawn against the low-stock alert level, amber with a word when at or under it, the same bar in table, sheet and product page.
PATH: filter → row (click or arrow keys) → record beside the list → edit in place or Open full page; New product opens the sectioned form, saving lands on Images.
RISK: the record pane is narrow for the form; below 1280 px rows open the product page instead.
