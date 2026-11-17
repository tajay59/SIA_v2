# 11. App flows

[← API](10-api.md) · [Manual home](README.md) · [Next: Design system →](12-design-system.md)

Source: [App Flow Document (APD)](../APD.md). It shows what happens on each click and which screen comes next in SHOP, SIA and SIA Mobile. Screen ids: `S-` SHOP, `A-` SIA, `M-` Mobile, `J-` journeys. Routes follow **file-based routing** (`/requests/[id]` = `src/pages/requests/[id].vue`). Request buttons come from the API's `allowedActions`.

## 11.1 Global behaviour (all apps)

| Situation | Behaviour |
|---|---|
| Not logged in on a guarded route | → Login with `?returnTo=<route>`; after login, return there |
| Login with a non-ACTIVE account | `ACCOUNT_PENDING_VERIFICATION` → Verify email · `ACCOUNT_PENDING_APPROVAL` → "Awaiting approval" · `ACCOUNT_REJECTED` / `ACCOUNT_SUSPENDED` → message with a contact link · `ACCOUNT_LOCKED` → message with the unlock time · `MFA_REQUIRED` → code step |
| Role not allowed (e.g. customer opens SIA) | SIA/Mobile: "This app is for CIMH staff" + link to SHOP. SHOP staff-only pages don't exist |
| Staff opens an admin-only page (SIA) | → dashboard with a toast naming the page: "“Audit log” is for administrators only. Ask an administrator if you need something there." (no silent jump) |
| Record ids on screen (SIA) | Lists show a short reference (`shortRef`, web-app: `ORD…3f9a2c`, the last six characters); the record's own header shows the full id with Copy. Meanings are never only in a tooltip (Held legend on A-13; full unit codes on unit cards, Pick Order lines and Who has what) |
| `@cimh.edu.bb` user in SHOP | Can browse. Cart icon hidden; "Add to request" replaced by a note: "CIMH staff can't submit requests" |
| Session expired mid-use | Silent refresh. If refresh fails → Login (`returnTo`), and unsaved form data is kept in session storage |
| 404 / not visible | "Not found" page with a link back (hidden resources look the same as missing ones) |
| 409 version conflict | Toast: "This was changed by someone else", then ↺ reload. The user's draft is kept where possible |
| 422 validation | Inline field errors from `errors[]` |
| 429 | Toast with the `Retry-After` countdown |
| 503 / network | Banner "Service unavailable, try again" + Retry. Nothing was saved |
| Empty lists | Explanatory empty state with the next action (e.g. "No requests yet → Browse catalogue") |
| Loading | Skeletons for lists and detail; buttons show a spinner and are disabled while submitting |
| Incomplete forms | Submit buttons are **not** disabled for missing input: pressing one marks every missing or wrong field and puts the cursor in the first (`checkForm`). A save button is disabled only when nothing has changed, and the save bar says so. Exception: small dialogs whose single field carries the hint (reason dialogs; Erase account, where typing the email is the safeguard) |
| Actions that can't be undone, or that email someone | Ask first in a dialog that names the record and what happens (send quote, return a unit, remove an address, erase, merge). The safe button is named for what it keeps ("Keep editing", "Keep issued") |
| Narrow screens (SIA) | No page scrolls sideways at 360 px; tab strips and chip rows scroll in place and keep the active tab on screen. Tables that would clip become stacked entries: the request timeline in narrow panels, quote-builder lines (two rows below 900 px of panel, cards below 600; laid out by panel width, not window width). Long lists are capped: the dashboard queue shows 10 on phones with a link to the desk, the Places tree 40 sites with "Show all" (the open site always listed). A record opened "beside" a list (`?open=`) goes to its own page on narrow screens. Emails keep their domain whole; only the part before @ is shortened |
| Theme | Light/dark toggle, remembered per device |

## 11.2 SHOP: screens

![SHOP navigation map](images/19-shop-sitemap.svg)

**Top bar:** logo → S-01 · Catalogue · Pro Bono · search box → S-06 · Cart (badge; customers, and visitors who are sent to log in first; not CIMH accounts) → S-07 · **Orders** → S-10 (page name "Orders", owner 2026-11-16) · Account menu (Profile, Log out) or Log in / Sign up.

| ID | Route | Screen | Guard | Main content | Actions → next |
|---|---|---|---|---|---|
| S-01 | `/` | Home | public | Hero carousel (the only large headline; no auto-advance, arrows + dots); **institute masthead** (deep navy field, white CIMH crest, one line on what the store is, the visitor's next step: Sign up / Log in, or Orders / catalogue); **Find your equipment**: a photo tile per equipment family that has items (radar large; two or three real item names, no counts; a failed tile shows **Retry**) and a yellow Pro Bono tile; **How requesting works** (4 steps on one path: approved account → request without prices → quote valid 30 days → signed agreement and delivery, drawn once on first view) with the Pro Bono branch (no quote); folded to one line for signed-in customers. Phones: one-column family rows with thumbnails, steps down the left edge | Family → S-02 (filtered) · Whole catalogue → S-02 · Pro Bono → S-04 · Sign up → S-13 · My requests → S-10 |
| S-02 | `/catalogue` | Catalogue | public | Search desk: navy band with title, one wide search (make, model or model number; matches marked in results), family index (All · Meteorological · Radar: SHOP shows only MET and RAD plus Pro Bono of any type), In stock only, Filters (department, project); same-height cards (photo on a white plate, or the part's nameplate), "Load more" (cursor) | Product → S-03 · Search → S-06 |
| S-03 | `/catalogue/[id]` | Product detail | public | Images, specs, availability (**no price**), Pro Bono badge and max per request, "How requesting works" (folded). **No photos:** no photo area; name, make/model, description and details take the main column | Quantity + **Add to cart** (customer) ↺ cart badge, toast "Added … to your cart" with "View cart" → S-07 · Not logged in → **Log in to request** S-16 (`returnTo`) or Register → S-13 |
| S-04 | `/pro-bono` | Pro Bono items | public | Same as S-02 (yellow rule and badge), filtered to `probono=true`; the index lists projects | → S-03 |
| S-06 | `/search?q=` | Search results | public | Ranked results, filters | → S-03 |
| S-07 | `/cart` | Cart | customer | Lines (snapshot, qty stepper with a typed quantity (0 removes), remove) under "Items to be quoted"; Pro Bono lines grouped separately; notes: "Paid and Pro Bono items become two requests", "Nothing is paid here". Layout "Progress rule" (2026-11-16): navy band with the request path Cart → Invoice → Delivery → Sent as four nodes on one rule that fills as the customer goes (done nodes go back), one question per screen under it; step 1 = lines beside a request slip | Qty change ↺ · Remove ↺ · **Continue to invoice** → S-08 · Add more items / Empty → S-02 |
| S-08 | `/cart` (steps 2–3) | Submit request | customer | Step **Invoice** ("Who is the quote made out to?"): invoice address as tiles (every saved address, or a new one). **A new address is saved to the account** (`PATCH /me`, max 10; an identical one is just picked; full list or a failed save = used for this request only) and is offered in later requests and in Account. **No currency question**: every quote is in BBD (owner, 2026-11-16). Step **Delivery** ("Where should it go?"): tiles "The invoice address" / "Another address" (then saved addresses + new), notes; beside it a "Check before you send" sheet (navy head with the item count; items × qty grouped quoted / Pro Bono, invoice and delivery addresses as address blocks, each part with Change back to its step; quote in BBD, the note; "not a commitment to pay"; **Send request** at its foot) | **Send request** → S-09 · Back → S-07 · Continue / Submit without an address → the missing address is named beside it |
| S-09 | `/cart` (step 4) | Request submitted | customer | One or two request ids, "What happens next" | View request → S-11 · Continue browsing → S-02 |
| S-10 | `/requests` | Orders | customer | **Docket** (2026-11-16): navy band with the title and tabs **Mine / My organisation**; list grouped by whose move it is with counts: **Waiting for you** (own requests with a quote to review or an agreement to sign, "valid until" + days left), With CIMH, On its way, Done; rows titled by what was requested (first item "and n more"), state + sent date, `shortRef` id, Pro Bono badge. Filters status, year (only once there is something to filter). **Wide screens (≥ 1100 px): the open request beside the list** (`?open=<id>`, default = first waiting, else newest); narrower: rows open S-11. Empty with filters set → **Clear filters** | Row → S-11 (beside, or own page) |
| S-11 | `/requests/[id]` | Request detail | customer (owner or same org) | Shared `RequestSheet` (also beside the S-10 list). Full id + sent date, title = what was requested, status chip; **request path** (Sent · Quote · Agreement · Ordered · Shipped · Delivered; Pro Bono: Sent · Approved · Picking · Shipped · Delivered) filled to where it stands (hidden once closed); **whose-move well** (customer's turn = primary tone + action and quote expiry; waiting on CIMH = neutral; amber when the quote expires within 7 days; green accepted/delivered; red closed). **Quote first while QUOTED / AWAITING_AGREEMENT** (labelled **Agreement total**, chosen option marked); then Status timeline, Items (Pro Bono marked Free), Delivery (address, currency, carrier, tracking link), Files (CIMH documents by kind) as ruled sections; decline / cancel at the foot. Own page: navy band with "← Orders". Slim footer | **Choose options** (QUOTED) → S-12 · **Decline** ⧉ reason → ↺ · **Cancel** ⧉ reason → ↺ · Tracking link → carrier site (new tab) · Document → download |
| S-12 | `/requests/[id]/agreement` | Choose and sign | requester | Step 1: radio CIMH/SUPPLIER per line with both options, live total (phones: one card per line with full-width option tiles). **Summary** on every step (chosen source and amount per line, admin fee, total, valid until, ship-to): beside the stepper on wide screens, first on phones in steps 2–3. Step 2: **Download agreement** (PDF, appears when generated; ↺ polling). Step 3: what happens next (staff check the signature, CIMH stock reserved, supplier items ordered and shipped direct) + **Upload signed agreement** (scan or phone photo; PDF/JPG/PNG, ≤ 20 MB) Confirm choices is never disabled: with lines still open it says so and focuses the first one. | Confirm choices → step 2 (status AWAITING_AGREEMENT) · Change choices → step 1 (new agreement) · Upload → **Accept** → S-11 (ACCEPTED, toast) · Cancel → S-11 |
| S-13 | `/signup` | Sign up | public | Three steps as tabs with a sliding indicator, panes slide in the direction of travel (You · Organisation (CIMH emails: Details) · Password; each Continue checks only its step, a server 422 jumps to the step of the first bad field); the picture lists the way to an approved account (form → email code → admin approval, usually two working days → requests). Name, email, password (strength + breach check message), organisation (free text), department, country, phone, terms | Submit → S-14 |
| S-14 | `/verify?email=` | Verify email | public | 6-digit code, resend (cool-down) | Correct → S-15 (member) or S-16 with "Account active" (`@cimh.edu.bb`) · Wrong → inline error (attempts left) |
| S-15 | `/pending-approval` | Awaiting approval | public | "An administrator will review your account; you'll get an email" | **Browse the catalogue** → S-02 · Home → S-01 |
| S-16 | `/login` | Log in | public | Email, password, (code if MFA); contact line "Trouble logging in? Write to info@cimh.edu.bb" (sign-in pages have no footer) | Success → `returnTo` or S-10 · Status errors as §2 · Forgot → S-17 · Sign up → S-13 |
| S-17 | `/forgot-password` | Forgot password | public | Email | Submit → S-18 (always, no enumeration) |
| S-18 | `/reset-password?email=` | Reset password | public | 6-digit code (six boxes, as S-14; no auto-submit) + new password | Success → S-16 "Password changed" |
| S-19 | `/account` | Your account | auth | **Account checklist** (impeccable 2026-11-16, owner's pick of three; brief `web/shop/.impeccable/surfaces/src-pages-account-vue.md`): navy band with name, email, organisation, role · status, Log out, and a checklist of where the account stands (email verified, approved by CIMH or "CIMH account", organisation linked by an administrator, saved addresses for customers, deletion requested); yellow ring = waiting on CIMH, dashed = for you. Below, one ruled row per section, read first (current values + one action): Personal details and Addresses (tiles, max 10, dashed Add tile) open in place, one at a time; Sign-in (change email, change password); Appearance (dark theme switch, this device); **Your data** (download, ask to delete). Logic: web-app `useProfile` (shared with SIA A-21) | Edit → Save details ↺ (If-Match; disabled only while nothing changed) / Cancel · Manage → Add / Edit address ⧉ · Remove address ⧉ (confirm; sent orders keep their copy) · Change email ⧉ → code step · Change password ⧉ · Download my data · Ask to delete ⧉ (password) · Log out → S-01 |
| S-20 | `/[...notFound]` | Not found | public | Message, catalogue search field, links (catalogue, Orders for customers, home); signed out: "log in to see it" with `returnTo` | → S-02 · S-10 · S-01 · S-16 |

## 11.3 SIA: screens (staff and admin)

![SIA navigation map](images/20-sia-sitemap.svg)

**Navigation** (legacy SIA top header; drawer below 1280 px): Dashboard · **Inventory** (`/products`, the product list with the low-stock count; was "Products") · **Locations** (`/inventory`: sites, locations, shelves, labels, lookup; was "Inventory", owner 2026-11-16) · Pick · Stow · **Orders** (request desk, `/requests`; owner 2026-11-16) · Reports ▾ · Admin ▾ · Profile. The **scan box** in the header takes a unit, shelf or product code (a handheld scanner types it and presses Enter) and opens Inventory → Lookup on it; request codes open the request desk once it exists (P5).

| ID | Route | Screen | Guard | Main content | Actions → next |
|---|---|---|---|---|---|
| A-01 | `/` | Dashboard | staff | Counters: new requests, quoting, agreements to verify, to purchase, to pick, to ship, quotes expiring ≤ 3 days, low stock, pending approvals (admin) "Products low on stock" and "accounts waiting for approval" become an amber cell (with "Restock board →") when the count is above 0. | Each counter → A-02 filtered / A-13 / A-16 |
| A-02 | `/requests` | Request desk (queue) | staff | Stage tabs with counts (Open, New, Quoting, Quoted, Awaiting signature, To verify, Pick & purchase, Shipped, Closed, All); search; More filters: statuses (multi), type, year, organisation, sort (default **newest first** by date sent, owner 2026-11-16; also waiting longest, oldest); queue + detail panels like A-01 (row: id, customer/org, next step, status, waiting with overdue > 5 days) Queue rows show the person's name, a Pro Bono badge when it is one and the organisation (no item name; owner 2026-11-16), `shortRef` (full id in a tooltip on hover) as the reference. | Row selects (detail panel acts); id link / Open full request → A-03; phones: tap → A-03 |
| A-03 | `/requests/[id]` | Request (staff) | staff | Customer + org, lines (with `cimhAvailable`, choice, reservation), timeline, documents, **action panel** driven by `allowedActions` While QUOTED the customer acts next, so Revise quote is an outlined (secondary) button; Pro Bono requests have no Invoiced step. Title = what was requested; under it customer · organisation · `shortRef` (full id on hover and copied by the button). Files panel without its own card (`RequestFiles bare`); timeline "By" shows the part before @ for actors without a name. | `start-quoting` ↺ → A-04 · `send-quote` (from A-04) · **Verify agreement** (view signed PDF ⧉) → `purchase-orders` ⧉ (supplier, PO no., lines, ☑ agreement verified) ↺ · `reject-agreement` ⧉ reason ↺ · `approve` / `reject` (Pro Bono) ↺ · **Pick** → A-10 (prefilled) · `ship` ⧉ carrier, tracking (not for HAND), note, cost, date, notify ↺ · `deliver` ⧉ ↺ · `cancel` ⧉ ↺ |
| A-04 | `/requests/[id]/quote` | Quote builder | staff | Per line: CIMH option (if fully in stock: cost + admin fee, auto-priced), supplier price inputs per supplier, upload supplier PDFs; each supplier quote is **BBD or USD** (USD: staff type the supplier's USD prices + a BBD-per-USD rate; the customer sees BBD with "Supplier quote: USD x each at r BBD per USD" and the supplier's file); **exchange rate** only on legacy USD requests with a CIMH option; totals; draft autosave (`quote-draft`) Summary: admin fee 0 reads "None set"; a range shows two rows (Agreement total, lowest / highest). Header shows `shortRef`. | **Send quote…** ⧉ confirm (recipient, quote version, lines priced, totals, "can't be recalled") → **Email the customer** → A-03 (QUOTED; customer emailed) · Incomplete → inline errors |
| A-05 | `/products` | Products | staff | Filter strip (search incl. serials, type chips, More filters: department, shown to customers, Pro Bono, inactive), product list (rows or photos) with a stock meter; wide screens open the full A-07 record beside the list (`?open=<id>`) Stock meter states: a number + bar; "Low" amber at or under the alert; zero = "None" in red with an alert level, neutral without one; no stock record = "Not counted" (no number, no bar). The list drops the Model number column when no product on the page has one. | Row → A-07 beside the list (own page on narrow screens) · New → A-06 |
| A-06 | `/products/new` | New product | staff | Form in sections (all ProductInput fields; **Pro Bono** choice required, max per request when on) + **Photos** section: add (pick or drop, JPEG/PNG/WebP ≤ 20 MB, up to 10), preview, reorder, make primary, remove, background-removal option; photos stay in the browser until Create | Create → product created, photos uploaded (primary first) → A-07 Images tab showing them as Processing… until media-worker finishes |
| A-07 | `/products/[id]` | Product | staff | Header (name, stock meter vs alert level, Create labels); tabs Overview (photos, description, facts, shelves), Edit details (sectioned form; Deactivate isolated below it), Images (upload, background-removal option, set primary, remove), Stock (by location), History | Save ↺ · Deactivate ⧉ · Create labels → A-12 (prefilled) |
| A-08 | `/inventory?code=<site or location>`, `?op=site` | Inventory: **Places** tree + record (storeroom map) | staff | Scan field + product search on top; left, tree site → location → shelves (always shown); right, the open place: site (locations + Add a location), location (shelf grid, shelf QR codes, Add shelves), or Register site | Register site → opens the site · Create location → opens the location · Add shelves (new shelves' QR sheet shown inline) · Shelf → A-11 · a location opened by its code alone finds its site and opens (site added to the URL) |
| A-09 | `/stow` → `/pick?op=stow` | Stow (now the **Stow · Relocate** tab of A-10) | staff | `/stow` redirects to the A-10 tab (old links and bookmarks keep working). See A-10 | — |
| A-10 | `/pick` | Pick (tabs; opens on Pick Order) | staff | Tabs **Pick Order** · **Pick** · **Stow · Relocate** · **Issue / Return**. **Pick Order**: queue "Ready to pick" (APPROVED, PICKING, PURCHASING; oldest first; scan/type a request id) beside the open request (Unit scan, lines with reserved units and progress, picked of total). Every tab: set-up rail left, work pane right (Unit scan + scan log), stacked on phones. **Pick**: Purpose rail (chips Repair, Station visit, Calibration, Loan, or free text); a scan without a reason is logged as refused. **Stow · Relocate** (A-09 folded in, `?op=stow` or `?op=relocate`): shelf rail (scan, validated, then a shelf card "Putting units on Shelf n" with Location, Site, the count put on this shelf, Change shelf); each unit scan stows it there, or moves it there when it already sits on another shelf (stow refused with `UNIT_ALREADY_STOWED` → relocate); Change shelf keeps the log, each entry names its shelf, and a refused scan is retried on the shelf it was scanned for. **Issue / Return**: mode + person rail (legacy self-stow); a return links to Stow · Relocate. Pick Order lines list each reserved, unpicked unit with where it sits (Site › Location › Shelf n). On the Pick tab the Unit field stays plain with a dashed edge until a purpose is chosen | Scan ↺ (Retry: same Idempotency-Key after a connection or server error, a new one after a refusal) · Request done → A-03 |
| A-11 | `/inventory?code=` (old `?op=lookup&code=` still works) | Inventory: record beside the Places tree | staff | Scan/enter a shelf (units, paged, shelf QR label), unit (card) or product code, or search a product by name (stock meter, counts, where it is by shelf); the tree marks the shelf | Unit card: Where links to its shelf; actions are outlined pill buttons with icons (open one filled): Move · Issue to a person · Return · Pick ↺ · Create labels → A-12 |
| A-12 | `/inventory?op=labels&product=` | Inventory: **Create labels** (beside the Places tree; products are created in A-06) | staff | Product, quantity, serials (optional, one per unit) | Create → QR label sheet (print) + legacy CSV + server PDF · Go to Stow · More labels |
| A-13 | `/reports/stock` | Stock levels | staff | Restock board: low stock (available ≤ alert level; none left first, then furthest under) with meter and held total, beside the open product's stock record (`?open=`): meter + verdict, reserved/issued/picked, units by site and shelf; the finder opens any product into the record A legend under the list says what Held means (reserved + issued + picked); the record splits it. | → A-07 Stock tab, A-12 labels, shelf on A-08 |
| A-14 | `/reports/assignments` | Who has what | staff | Graphite Console: filter strip (one person; unit and people counts), then one panel per person (most units first) with a row per unit (product link, unit code, serial, last on a shelf) and its own Return, kept on screen at 360 px (the button wraps under the text); empty state links to Issue / Return Filter "Person" (placeholder Everyone); person name as a title (not an uppercase eyebrow); unit codes shortened (`shortUnit`, full code on hover). | Return ⧉ (confirm names the unit and the person) ↺ |
| A-15 | `/reports/history` | Movement history | staff | Day ledger: movements grouped by Barbados day (newest first, count per day); rows = time, operation, unit, readable place (from → to), person/request/reason, who scanned. Filters: unit code, scanned by, date presets (any time, today, 7 days, 30 days, custom range), operation chips | → unit / shelf on A-08, request A-03 |
| A-16 | `/admin/approvals` | Pending accounts | admin | Review queue, oldest first: person + email (domain emphasised), organisation given, email domain, wait (amber "Overdue" after 48 h); suggested organisation match in the dialog; checkbox multi-select, bulk actions in the panel head Each row has a match line: the email domain belongs to an organisation on record, the name given matches one, a personal email (Gmail etc.) never counts, or no organisation yet (create one when approving). | **Approve** ⧉ (pick/create organisation, role) ↺ · **Deny** ⧉ reason ↺ · Bulk approve/deny ⧉ (207 results) ↺ |
| A-00 | `/admin` | Admin overview | staff (admin parts admin only) | "Needs an administrator": oldest 5 waiting for approval, every open deletion request (rows open the account beside the list); admin pages index | → A-16 · → A-17 (`?open=`) · links to A-17–A-21 |
| A-17 | `/admin/accounts` · `/admin/accounts/[id]` | Accounts | admin (staff read) | Filter strip (name/email prefix, role, "Asked to be deleted", status chips) + list; the account record opens beside it on wide screens (`?open=<id>`), own page on phones: header (status, role), Next step well (approve/deny, deletion request, suspended, admin without MFA), Profile + Sign-in and access facts, status history; actions at the foot (Suspend is reversible, a plain button); **Personal data** group apart: Export data and the only red button, "Erase permanently…" | Role ⧉ · Suspend ⧉ / Reactivate · Export data · Erase ⧉ (reason + type the email) · → A-20 filtered |
| A-18 | `/admin/organisations` | Organisations | admin (staff read) | Search + list (name, other names, type, country, domains, members); the organisation record opens beside it (`?open=<id>`, `?open=new` to create; alone with a way back below 1280 px): facts, members (first 20, linked to A-17), Edit details form with save bar, Merge a duplicate apart at the foot | New/Save · **Merge** ⧉ (confirm) target |
| A-19 | `/admin/settings` | Settings | admin | One frame: section index (`?tab=` fees · lists · workflow · reference, unsaved dot) beside the open section: Fees ledger (once per CIMH-stock request, total) · Email lists (who, count, warning when a list is empty) · Workflow grouped Quotes/Accounts/Carts with explanations · Reference (departments; projects incl. inactive, rename, toggle, add); sticky save bar per section; one save model: every edit waits for the section's Save (project names and Active included; only Add project acts at once) | Save ↺ · Leaving with unsaved sections ⧉ "Leave without saving?" (lists them; also on tab close) |
| A-20 | `/admin/audit` | Audit log | admin | Day ledger (Barbados days, newest first): filters action, record id, date presets (Any time/Today/7/30 days/Custom), record kind chips, all in the URL; entry = time, action in words + code, from → to, reason, record, who + role Entries read in words: action as a sentence (code kept small for the filter), people and organisations by name, services as "System", change details as "Field: value" (never JSON); runs of 2+ routine sign-in entries fold into one line with "Show them". | Record link → A-17 / A-18 record |
| A-21 | `/login` · `/signup` · `/profile` | Login / Sign up / Profile | public / staff | As S-16 / S-19; non-staff → "staff only" message. **SIA sign-up** (owner, 2026-11-16): as S-13 but only @cimh.edu.bb addresses; after the email code an administrator gives the account staff access. Sign-in pages: graphite form side (whatever theme is stored) with the SIA mark + "SIA · Staff app" beside the picture. Profile: Graphite Console panels (Personal details, Sign-in, Appearance, Your data) | — |

## 11.4 SIA Mobile: screens (Android 12+)

![SIA Mobile navigation map](images/21-mobile-sitemap.svg)

**Bottom navigation:** Home · Lookup · Stow · Pick · Orders. The overflow menu holds Create product, Create location, Sync queue and Log out (with a badge for queued or refused scans).

| ID | Route | Screen | Main content | Actions → next |
|---|---|---|---|---|
| M-01 | `login` | Login | Email, password, (code) | Success → M-02 · non-staff → "staff only" |
| M-02 | `home` | Home | Shortcuts, **offline queue badge**, last sync | → any tab |
| M-03 | `lookup` → `lookup/results` → `product/{id}` | Lookup | Camera scan (shelf/product) or type; results paged; product with locations | Unit → unit sheet (relocate, assign) |
| M-04 | `stow` | Stow | Scan shelf → scan units loop; vibration + sound per result | Done → M-02 |
| M-05 | `pick` | Pick · Issue · Return | Pick: reason once, then scan units. Issue: choose a person (name or email), then scan units. Return: scan units coming back (then stow them) | Next scan ↺ |
| M-06 | `orders` | Orders to pick/ship | Requests with lines to pick or ship (paid PURCHASING with CIMH-stock lines; Pro Bono APPROVED or PICKING; same filter as the SIA web "To pick" tile) | Row → M-07 |
| M-07 | `orders/{id}/pick` | Pick order | Lines (CIMH/Pro Bono only) with progress; scan units; wrong unit → error chip | All picked → M-08 |
| M-08 | `orders/{id}/ship` | Ship | Carrier, tracking (camera scan of the label barcode), note, date | Ship → M-06 |
| M-09 | `create/product` | Create product | Form + photos (camera) | Save → product/{id} |
| M-10 | `create/location` | Create location | Site → location → shelves | Save ↺ |
| M-11 | `sync` | Sync queue | Queued scans with status; retry/discard failed | ↺ |

**Offline:**
- Every scan (stow, pick, relocate) is saved first, with its own `Idempotency-Key`, in Room. It is then sent at once, or by WorkManager when the connection returns. The key never changes on automatic retries, so a scan that reached the server before the connection dropped is not done twice.
- Scans are sent oldest first, and a new scan never overtakes a queued one (a stow and a later pick of the same unit arrive in that order).
- No answer, 408, 429 or 5xx: the scan stays queued. 401: sending stops until the same account logs in again. Any other 4xx: the scan is **refused** and kept in M-11 with the server's message. The server replays a refusal for the same key, so **Retry** in M-11 sends it with a new key; **Discard** deletes it.
- The UI shows Done / Queued / Refused chips. M-02 shows the queue count and the last sync time; the overflow menu shows a badge.
- Log out with scans still in the queue asks first: the queue belongs to the account that scanned and is deleted on log out. Scans of another account are never sent with the current account's token.
- Scan input: live camera (CameraX + ML Kit on the device), or a text field that submits on Enter, for Bluetooth/USB scanners and damaged labels.

## 11.5 User journeys

### J-01 Registration and approval

![Registration journey](images/24-journey-registration.svg)

| Step | Who / screen | Action | Result / next |
|---|---|---|---|
| 1 | Visitor · S-13 | Fills sign-up | Account `PENDING_VERIFICATION`; code emailed → S-14 |
| 2 | Visitor · S-14 | Enters code | `@cimh.edu.bb` → `ACTIVE` → S-16 · otherwise `PENDING_APPROVAL` → S-15; admins emailed |
| 3 | Admin · email link → A-16 | Approves (links organisation, role) or denies (reason) | User emailed; approved → can log in at S-16 |
| 4 | User · S-16 | Logs in | → S-10 or `returnTo` |
| Alt | User · S-16 before approval | Logs in | "Awaiting approval" (S-15) |
| Alt | Code expired / lost | Resend on S-14 | New code (max 3/hour); unverified 24 h → `EXPIRED` (must register again) |

### J-02 Browse → cart → submit

![Cart to submission journey](images/25-journey-quote-acceptance.svg)

| Step | Screen | Action | Next |
|---|---|---|---|
| 1 | S-01/S-02/S-04/S-06 | Find a product | S-03 |
| 2 | S-03 | Add to cart (qty; Pro Bono capped) | Toast; badge ↺ |
| 3 | S-07 | Review, adjust | S-08 |
| 4 | S-08 | Invoice address, delivery address, notes → Send | S-09 (1 or 2 requests) |

### J-03 Quote → choose → sign → accepted (customer)

Same diagram (lower half).

| Step | Screen | Action | Next / status |
|---|---|---|---|
| 1 | Email "Quote ready" → S-11 | Reads supplier and CIMH options, expiry | — |
| 2 | S-11 → S-12 step 1 | Chooses CIMH/SUPPLIER per line → Confirm | `AWAITING_AGREEMENT`; agreement PDF generated |
| 3 | S-12 step 2 | Downloads agreement, signs | — |
| 4 | S-12 step 3 | Uploads signed copy → Accept | `ACCEPTED` → S-11 |
| Alt | S-12 | Change choices | Back to step 1 (new agreement) |
| Alt | S-11 | Decline with reason | `DECLINED → CANCELLED` |
| Alt | — | Quote expires (30 d) | `CANCELLED` (auto); reminder 3 days before |
| Alt | Email "Signature rejected" → S-12 step 3 | Uploads again | `ACCEPTED` |

### J-04 Track to delivery (customer)

S-10 (badge) → S-11: timeline updates (PURCHASING → SHIPPED with carrier and tracking link → DELIVERED). Invoice appears under Documents. Organisation colleagues can follow from the **My organisation** tab.

### J-05 Staff: quoting

![Staff request desk journey](images/26-journey-staff-desk.svg)

| Step | Screen | Action | Result |
|---|---|---|---|
| 1 | A-01 "New requests" → A-02 → A-03 | Start quoting | `QUOTING`; lines show CIMH availability |
| 2 | A-04 | Upload supplier PDFs, enter prices (supplier currency; rate for USD) | Draft autosaved |
| 3 | A-04 | Send quote | `QUOTED` (30 d); customer emailed → A-03 |
| Alt | A-03 (QUOTED) | Revise → A-04 → Send | New quote version |

### J-06 Staff: fulfil a paid request

| Step | Screen | Action | Result |
|---|---|---|---|
| 1 | A-01 "Agreements to verify" → A-03 | Open signed agreement ⧉ | — |
| 2a | A-03 | Not acceptable → Reject signature (reason) | `AWAITING_AGREEMENT`; customer emailed |
| 2b | A-03 | ☑ verified + purchase orders | `PURCHASING` |
| 3 | A-10 / M-07 | Pick **CIMH-stock lines** (supplier items ship direct) | Lines picked |
| 4 | A-03 / M-08 | Ship: carrier, tracking (not HAND), notify | `SHIPPED`; customer emailed |
| 5 | A-03 | Deliver | `DELIVERED`; invoice generated |

### J-07 Pro Bono request

A-02 (type Pro Bono) → A-03: **Approve** (reserves stock) or **Reject** (reason) → pick (A-10/M-07, `PICKING`) → ship → deliver. Customer screens are S-10/S-11 (no quote panel).

### J-08 Admin approvals

A-01 "Pending approvals" or email → A-16. For each account: check the organisation text and email domain; the suggested organisation match is shown → **Approve** ⧉ (pick or create organisation, role) or **Deny** ⧉ (reason). Bulk mode takes up to 100. A reminder email is sent if an account has waited more than 48 h.

### J-09 Warehouse scanning (mobile)

![Mobile scanning journey](images/27-journey-mobile-scan.svg)

| Flow | Steps |
|---|---|
| Stow | M-04: scan shelf → (valid) → scan unit → ✓ chip / ✗ error (not found, already stowed) → repeat → Done |
| Pick | M-05: scan unit → reason → ✓ / ✗ (reserved for a request → use Orders) |
| Pick order | M-06 → M-07: scan units per line → wrong unit ✗ (`UNIT_NOT_RESERVED_FOR_ORDER`, `LINE_NOT_PICKABLE`) → all lines done → M-08 ship |
| Offline | Any scan with no connection → queued ✓ (grey) → synced later; failures in M-11 |

### J-10 Product with images (staff)

A-05 → New → A-06 (Pro Bono toggle required) → Save → A-07 Images tab → upload (optional background removal) → "processing" placeholders → images appear (↺ via polling or a refresh) → set primary.

### J-11 Password reset

S-16 "Forgot" → S-17 (email) → S-18 (code + new password) → S-16 "Password changed". All sessions are revoked.

## 11.6 Email → screen deep links

| Email | Link opens |
|---|---|
| Verification code | S-14 (`?email=`) |
| Awaiting approval / approved / rejected | S-15 / S-16 / S-01 |
| (Admins) Account waiting / reminder | A-16 |
| (Staff) New request | A-03 |
| Quote ready / reminder / expired | S-11 |
| Agreement ready | S-12 (step 2) |
| Signature rejected | S-12 (step 3) |
| (Staff) Signed agreement received | A-03 |
| Shipped (with tracking) / delivered (invoice) | S-11 |
| Cancelled | S-11 |
| (Staff) Low stock | A-13 |
| (Staff) Reservation failed | A-04 |

Links that need a login go through S-16 / A-21 with `returnTo`.

## 11.7 Questions

| # | Question | Outcome |
|---|---|---|
| 1 | Saved or multiple carts? | **Resolved:** no. One cart per user. |
| 2 | Per-staff assignment / "my work" on the dashboard? | **Resolved:** no. Requests have no assignee; the dashboard shows shared queues. |
| 3 | Is the Pro Bono catalogue public? | **Resolved:** yes, visible to anyone (S-04 guard `public`). Requesting still needs an approved customer account. |

## 11.9 Implementation status (2026-11-07)

Code: `web/shop`, `web/sia` (Vue 3 + Vuetify 4 + Vue Router 5 file-based routes), shared `packages/web-app` (session store, API errors and silent refresh, route guards, forms). Built and tested with Playwright (`tests/e2e-web`: J-01, J-08, J-10, J-11, personal data and the §2 behaviours) on every PR; deployed to staging (store.hashiz.store, sia.hashiz.store).

| Built | Notes |
|---|---|
| S-13 – S-19, S-20 | As specified. S-16 handles every account-state code of §2 |
| S-01 | Hero carousel (owner's image, radar, AWS; plain copy) unchanged; below it (impeccable redesign 2026-11-16, "Masthead + index"): masthead, family index, request path (`components/HowRequestingWorks.vue` `variant="band"`, also folded on S-03 as `list`). Surface brief `web/shop/.impeccable/surfaces/src-pages-index-vue.md`. Footer = legacy SHOP footer content and layout (`ShopFooter.vue`). Hero files in `web/shop/src/assets/hero/` |
| S-02, S-04, S-06 | "Search desk" (impeccable 2026-11-16; brief `web/shop/.impeccable/surfaces/src-components-cataloguebrowser-vue.md`): `CatalogueBrowser` navy band (search, sliding index ink), `ProductGrid`, `ProductCard` (4:3 tile, nameplate when no photo, one status line); search results on the same page (`/search` redirects to `/catalogue?q=`) |
| S-03 | "Gallery band" (impeccable 2026-11-16, owner's pick of three): breadcrumb (catalogue › family); a full-width band shows the part first (photo on a white plate, counter, thumbnails along its foot, arrows; ends on the logo-blue rule); **no photo** = the catalogue's navy field with a large nameplate (make + model, else model number, else "No photo yet"; never the heading). Then one request bar: name, make, mono model number, badges (stock, Pro Bono limit), units per pack, quantity + **Add to cart** (Pro Bono note: CIMH approves, no quote); the bar pins under the app bar once the band scrolls away (phones: name + Add to cart). Description | Specifications below, "How requesting works" folded. Motion: plate settles on load, quantity rolls, added parts fly from the button into the cart icon (reduced motion: the cart flashes); toast with "View cart" |
| A-05, A-06, A-07 | Graphite Console list beside record (owner choice 2026-11-12, replaces the legacy structure): filter strip, product list, `components/ProductRecord.vue` beside it (also the `/products/[id]` page); shared `StockMeter` (available against the alert level, amber "Low", red "None"); form in sections with a section index and a sticky save bar |
| Shells | Legacy structure (owner rule 2026-11-07): SHOP = top bar on desktop, bottom navigation on phones, CIMH footer; sign-in pages = split sign-in (impeccable 2026-11-16 round 2, owner chose the category standard, bar Stripe/Linear/Notion; `AuthCard`): a picture inset in a rounded frame (caption chip; optional silent looping video with Pause; owner-generated `assets/auth/shop|sia.webp`, legacy enclosure photo until then) beside the form column (SHOP white, SIA graphite) with crest + app name, heading, line, form, footer links; phones: the picture is a 200 px band on top. Moving between sign-in pages is a View Transition: the picture holds still, the column's words lift out and settle in. No top bar, bottom navigation or footer; the crest links home; SIA = one horizontal header with an Admin menu (no side drawer). Sign-in pages (both apps) = the split sign-in above |
| A-01 | Legacy SIA Home structure: statement band, Radar / Hydro-Met spares cards, "What are you looking for today?" search, then the account counters |
| A-19 | Fees, email lists (active staff/admins), workflow, reference (departments; projects incl. inactive, rename, toggle) |
| S-10 Ids shown as `shortRef` (full on hover). | Empty state until order-svc (P5) |
| A-21, A-16, A-17, A-18, A-20 | As specified; A-16 suggests an organisation from the email domain, then the organisation text, and can create one in the dialog |
| Personal data (S-19, A-21, A-17) | "Your data" card: download (JSON) and ask to delete; A-17 marks and filters requests, exports and erases. The admin email for a request waits for notification-svc (P6) |
| A-01 | Identity counters only (pending approvals, unverified sign-ups) until order/inventory exist |
| **New:** `/mfa-setup` (SIA) | An admin without MFA lands here after login and can't use anything else (TR-AUTH-9). After confirming, the admin logs in again, because the old token predates MFA |
| Shortcuts, drafts (P7) | SIA: `/` focuses the page search (or the scan box), `s` the scan box (opens the drawer on small screens), `g r` Requests; ignored while typing or in a dialog. Unsaved forms (new/edit product, SHOP checkout) are kept in the tab's session storage, restored with a toast after logging back in, removed on save, Cancel or logout, ignored after 4 h |
| **New:** `/staff-only` (SIA) | The "This app is for CIMH staff" screen of §2 |
| **SIA Mobile** M-01 + session (`mobile/sia`) | New app (id `bb.edu.cimh.sia`) next to the legacy one. Login with MFA code step, "staff only" for customers, admins without MFA sent to SIA web; refresh token sealed in the Android Keystore; app lock after 5 min (screen lock or strong biometric; no screen lock → signed out); HTTPS only with pinned Let's Encrypt roots. M-02 is a placeholder; M-03–M-11 come with P8. CI job `mobile` (unit, lint, debug + release build) |

Behaviour notes: the start-up session probe never shows "session ended" to an anonymous visitor (only a failed refresh during use does). Dev servers use ports 15173 (SHOP) and 15174 (SIA).
