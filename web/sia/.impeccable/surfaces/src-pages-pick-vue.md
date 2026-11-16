---
primaryTarget: src/pages/pick.vue
mode: operate
---
# /pick surface brief

Desk PC + USB (keyboard-wedge) scanner; Pick Order is the most frequent job (owner, 2026-11-12). The four operations stay: Pick Order, Pick, Relocate, Issue / Return.

## Direction contract
THESIS: The page opens on the work, not a menu: requests waiting to be picked, oldest first, beside the open request. Refuses the "choose an operation" card grid and the type-a-request-id start.
OWN-WORLD: SIA dark console (console.css panels, Inter, JetBrains Mono codes, primary #5CC2FF, success green for full lines, Pro Bono yellow chip). Underline tabs (owner: the tab buttons from the "Tabs and live log" sketch).
STORY: Staff see what is waiting and for how long, open the oldest, scan its units until every line is full, then go to the request to ship.
FIRST VIEWPORT: Title + underline tabs (Pick Order first). Left 360-400 px rail "Ready to pick" (scan/type a request id on top; rows: mono id, Pro Bono chip, waiting time, customer, lines + status). Right: Unit scan bar on top, customer heading with big picked/total, line cards with progress bars and reserved unit codes, newest scan result + tally.
FORM: Pick queue, dealt structure 1 of 7 (operate surface round); seed:169deaa8152baaeb
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

## Extension (2026-11-12)
Pick, Relocate and Issue / Return inherit Pick Order's composition: the left column is a set-up rail (Purpose · Target shelf · Issue/Return mode + person) in the same panel as the queue, the right is the work pane (prominent Unit scan, scan log, empty state until set-up is complete). Copy avoids "left/right" because phones stack the rail above the pane.
