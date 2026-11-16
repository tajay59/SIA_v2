---
version: 1
slug: "src-app-vue"
primary_target: "src/App.vue"
related_targets: ["src/pages/index.vue"]
---

Scope: SIA staff app (web/sia), whole app shell + dashboard first, then every SIA page. Mode: Operate.
Audience: CIMH stores staff/admins; desk work and storeroom floor (phones). Owner pinned: left navigation drawer, no top nav bar; dark default with a light variant.

## Direction contract
THESIS: Persistent panels on graphite: drawer, work queue and the selected item's detail stay on screen; navigation changes panel contents. Refuses the storefront hero + KPI-card grid default.
OWN-WORLD: Graphite ground (#16191D), panels one step up (#1C2026/#22272E), 1px seams (#30363D), no shadows. Text #E6EDF3 / muted #9DA7B3. Action blue #5CC2FF (light #006FA8). State only: amber verify/approve, red expiring/failed, green done, Pro Bono #F5C400 ink text. Inter compact 13-14px; codes and figures JetBrains Mono; panel headers small caps. Light variant mirrors it (white panels, #D0D7DE seams).
STORY: Staff open SIA and see exactly what needs them, oldest first, act on it in the detail panel without losing the queue.
FIRST VIEWPORT: Left drawer 232px (Work/Stock/Admin with counts, scan box at foot). Queue panel 520px: count strip (New, Verify, Pick, Ship, Low stock) then "Needs you now" rows (code, customer, state word, waiting). Detail panel fills the rest with the selected request, primary action in blue, destructive outlined and isolated. Header line: Updated hh:mm with refresh.
FORM: Graphite Console (challenger digital-design-canon-dark-first-developer-console), chosen over assigned Harbour Manifest. Raises kept: state words never colour alone; waiting age shown; phone scan screens one task full-screen; destructive isolation. seed:e1d7b7d212786ba2
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
