# 11. App flows

[← API](10-api.md) · [Manual home](README.md) · [Next: Design system →](12-design-system.md)

Source: [App Flow Document (APD)](../APD.md). It shows what happens on each click and which screen comes next in SHOP, SIA and SIA Mobile. Screen ids: `S-` SHOP, `A-` SIA, `M-` Mobile, `J-` journeys. Routes follow **file-based routing** (`/requests/[id]` = `src/pages/requests/[id].vue`). Request buttons come from the API's `allowedActions`.

## 11.1 Global behaviour (all apps)

| Situation | Behaviour |
|---|---|
| Not logged in on a guarded route | → Login with `?returnTo=<route>`; after login, return there |
| Login with a non-ACTIVE account | `ACCOUNT_PENDING_VERIFICATION` → Verify email · `ACCOUNT_PENDING_APPROVAL` → "Awaiting approval" · `ACCOUNT_REJECTED` / `ACCOUNT_SUSPENDED` → message with a contact link · `ACCOUNT_LOCKED` → message with the unlock time · `MFA_REQUIRED` → code step |
| Role not allowed (e.g. customer opens SIA) | SIA/Mobile: "This app is for CIMH staff" + link to SHOP. SHOP staff-only pages don't exist |
| `@cimh.edu.bb` user in SHOP | Can browse. Cart icon hidden; "Add to request" replaced by a note: "CIMH staff can't submit requests" |
| Session expired mid-use | Silent refresh. If refresh fails → Login (`returnTo`), and unsaved form data is kept in session storage |
| 404 / not visible | "Not found" page with a link back (hidden resources look the same as missing ones) |
| 409 version conflict | Toast: "This was changed by someone else", then ↺ reload. The user's draft is kept where possible |
| 422 validation | Inline field errors from `errors[]` |
| 429 | Toast with the `Retry-After` countdown |
| 503 / network | Banner "Service unavailable, try again" + Retry. Nothing was saved |
| Empty lists | Explanatory empty state with the next action (e.g. "No requests yet → Browse catalogue") |
| Loading | Skeletons for lists and detail; buttons show a spinner and are disabled while submitting |
| Theme | Light/dark toggle, remembered per device |

## 11.2 SHOP: screens

![SHOP navigation map](images/19-shop-sitemap.svg)

**Top bar:** logo → S-01 · Catalogue · Pro Bono · search box → S-06 · Cart (badge; customers only) → S-07 · My requests → S-10 · Account menu (Profile, Log out) or Log in / Sign up.

| ID | Route | Screen | Guard | Main content | Actions → next |
|---|---|---|---|---|---|
| S-01 | `/` | Home | public | Hero, featured MET/RAD products, Pro Bono teaser, how requesting works (3 steps) | Product → S-03 · Browse → S-02 · Pro Bono → S-04 · Sign up → S-13 |
| S-02 | `/catalogue` | Catalogue | public | Filters (type, department, project, in stock), product grid, "Load more" (cursor) | Product → S-03 · Search → S-06 |
| S-03 | `/catalogue/[id]` | Product detail | public | Images, specs, availability (**no price**), Pro Bono badge and max per request | Quantity + **Add to request** (customer) ↺ cart badge, toast "Added" with "View cart" → S-07 · Not logged in → S-16 (`returnTo`) |
| S-04 | `/pro-bono` | Pro Bono items | public | Same as S-02, filtered to `probono=true`, by project | → S-03 |
| S-06 | `/search?q=` | Search results | public | Ranked results, filters | → S-03 |
| S-07 | `/cart` | Cart | customer | Lines (snapshot, qty stepper, remove); Pro Bono lines grouped separately; note: "Paid and Pro Bono items become two requests" | Qty change ↺ · Remove ↺ · **Continue** → S-08 · Empty → S-02 |
| S-08 | `/cart/submit` | Submit request | customer | Shipping address (saved list or new), billing (same as shipping by default), currency **BBD/USD** (only if paid lines), notes, review | **Submit** → S-09 · Back → S-07 |
| S-09 | `/requests/submitted` | Request submitted | customer | One or two request ids, "What happens next" | View request → S-11 · Continue browsing → S-02 |
| S-10 | `/requests` | My requests | customer | Tabs **Mine / My organisation**; filters status, year, requester; list with status chip and "action needed" badge (quote ready, agreement to sign) | Row → S-11 |
| S-11 | `/requests/[id]` | Request detail | customer (owner or same org) | Status timeline; lines; **Quote panel** (when QUOTED+): supplier quote(s) and the CIMH option side by side per line, totals, expiry countdown, PDFs; documents; shipping (carrier, tracking link); cancel | **Choose options** (QUOTED) → S-12 · **Decline** ⧉ reason → ↺ · **Cancel** ⧉ reason → ↺ · Tracking link → carrier site (new tab) · Document → download |
| S-12 | `/requests/[id]/agreement` | Choose and sign | requester | Step 1: radio CIMH/SUPPLIER per line with both options, live total. Step 2: **Download agreement** (PDF, appears when generated; ↺ polling). Step 3: **Upload signed agreement** (PDF/JPG/PNG, ≤ 20 MB) | Confirm choices → step 2 (status AWAITING_AGREEMENT) · Change choices → step 1 (new agreement) · Upload → **Accept** → S-11 (ACCEPTED, toast) · Cancel → S-11 |
| S-13 | `/signup` | Sign up | public | Name, email, password (strength + breach check message), organisation (free text), department, country, phone, terms | Submit → S-14 |
| S-14 | `/verify?email=` | Verify email | public | 6-digit code, resend (cool-down) | Correct → S-15 (member) or S-16 with "Account active" (`@cimh.edu.bb`) · Wrong → inline error (attempts left) |
| S-15 | `/pending-approval` | Awaiting approval | public | "An administrator will review your account; you'll get an email" | Home → S-01 |
| S-16 | `/login` | Log in | public | Email, password, (code if MFA) | Success → `returnTo` or S-10 · Status errors as §2 · Forgot → S-17 · Sign up → S-13 |
| S-17 | `/forgot-password` | Forgot password | public | Email | Submit → S-18 (always, no enumeration) |
| S-18 | `/reset-password?email=` | Reset password | public | Code + new password | Success → S-16 "Password changed" |
| S-19 | `/account` | Profile | auth | Name, phone, organisation (read-only + "contact admin"), addresses (max 10), change email, change password, theme, **your data** | Save ↺ (If-Match) · Change email ⧉ → code step · Download my data · Ask to delete ⧉ (password) · Log out → S-01 |
| S-20 | `/[...notFound]` | Not found | public | Message + links | → S-01 |

## 11.3 SIA: screens (staff and admin)

![SIA navigation map](images/20-sia-sitemap.svg)

**Side navigation:** Dashboard · Request desk · Catalogue · Inventory (Sites, Stow, Pick, Lookup, Labels) · Reports · Admin (admin only) · Profile. A **global scan box** accepts a unit, shelf or request barcode → opens the matching screen.

| ID | Route | Screen | Guard | Main content | Actions → next |
|---|---|---|---|---|---|
| A-01 | `/` | Dashboard | staff | Counters: new requests, quoting, agreements to verify, to purchase, to pick, to ship, quotes expiring ≤ 3 days, low stock, pending approvals (admin) | Each counter → A-02 filtered / A-13 / A-16 |
| A-02 | `/requests` | Request desk (queue) | staff | Filters: status (multi), type, year, organisation, customer, search; sort by **waiting time**; columns: id, customer, org, type, status, waiting days, expiry | Row → A-03 |
| A-03 | `/requests/[id]` | Request (staff) | staff | Customer + org, lines (with `cimhAvailable`, choice, reservation), timeline, documents, **action panel** driven by `allowedActions` | `start-quoting` ↺ → A-04 · `send-quote` (from A-04) · **Verify agreement** (view signed PDF ⧉) → `purchase-orders` ⧉ (supplier, PO no., lines, ☑ agreement verified) ↺ · `reject-agreement` ⧉ reason ↺ · `approve` / `reject` (Pro Bono) ↺ · **Pick** → A-10 (prefilled) · `ship` ⧉ carrier, tracking (not for HAND), note, cost, date, notify ↺ · `deliver` ⧉ ↺ · `cancel` ⧉ ↺ |
| A-04 | `/requests/[id]/quote` | Quote builder | staff | Per line: CIMH option (if fully in stock: cost + admin fee, auto-priced), supplier price inputs per supplier, upload supplier PDFs; **exchange rate** (USD requests with a CIMH option); totals; draft autosave (`quote-draft`) | **Send quote** → A-03 (QUOTED; customer emailed) · Incomplete → inline errors |
| A-05 | `/products` | Products | staff | Search, filters (type, department, sellable, Pro Bono, inactive), table with stock count | Row → A-07 · New → A-06 |
| A-06 | `/products/new` | New product | staff | Form (all ProductInput fields; **Pro Bono** toggle required, max per request when on) | Save → A-07 (then add images) |
| A-07 | `/products/[id]` | Product | staff | Tabs: Details (edit), Images (upload, background-removal option, set primary, remove), Stock (by location), History | Save ↺ · Deactivate ⧉ · Create labels → A-12 (prefilled) |
| A-08 | `/inventory/sites` | Sites and shelves | staff | Tree site → location → shelves; QR per shelf (print) | New site/location ⧉ · Add shelves ⧉ · Shelf → A-11 |
| A-09 | `/inventory/stow` | Stow | staff | Step 1 scan/enter **shelf**; step 2 scan **units** (repeat); running list | Each scan ↺ (success/fail chip) · Change shelf → step 1 |
| A-10 | `/inventory/pick` | Pick | staff | Mode **Reason** (scan unit + reason) or **For request** (request id → lines; scan units per line; only CIMH/Pro Bono lines) | Scan ↺ · Request done → A-03 |
| A-11 | `/inventory/lookup` | Lookup | staff | Scan/enter shelf or product → units (paged) / locations | Unit → unit ⧉ (relocate, assign) |
| A-12 | `/inventory/labels` | Labels | staff | Product, quantity, serials, PDF/CSV | Create → download |
| A-13 | `/reports/stock` | Stock levels | staff | Low stock first; per product available/reserved/picked | → A-07 |
| A-14 | `/reports/assignments` | Who has what | staff | Units issued to people | Unassign ⧉ |
| A-15 | `/reports/history` | Movement history | staff | Filters unit, user, operation, dates | — |
| A-16 | `/admin/approvals` | Pending accounts | admin | Oldest first; organisation text, email domain, suggested organisation match; checkbox multi-select | **Approve** ⧉ (pick/create organisation, role) ↺ · **Deny** ⧉ reason ↺ · Bulk approve/deny ⧉ (207 results) ↺ |
| A-17 | `/admin/accounts` · `/admin/accounts/[id]` | Accounts | admin (staff read) | List with filters (incl. "asked to be deleted"); detail with status history | Role ⧉ · Suspend ⧉ / Reactivate · Export data · Erase ⧉ (reason + type the email) · → A-20 filtered |
| A-18 | `/admin/organisations` | Organisations | admin | List, members, aliases, domains | New/Edit ⧉ · **Merge** ⧉ target |
| A-19 | `/admin/settings` | Settings | admin | Tabs: Fees (admin fee) · Email lists · Workflow (quote validity, reminders, purge, cart inactivity) · Reference (departments, projects) | Save ↺ |
| A-20 | `/admin/audit` | Audit log | admin | Filters entity, actor, action, dates | Entity link → its screen |
| A-21 | `/login` · `/profile` | Login / Profile | public / staff | As S-16 / S-19; non-staff → "staff only" message | — |

## 11.4 SIA Mobile: screens (Android 11+)

![SIA Mobile navigation map](images/21-mobile-sitemap.svg)

**Bottom navigation:** Home · Lookup · Stow · Pick · Orders. The overflow menu holds Create product, Create location, Sync queue, Settings and Log out.

| ID | Route | Screen | Main content | Actions → next |
|---|---|---|---|---|
| M-01 | `login` | Login | Email, password, (code) | Success → M-02 · non-staff → "staff only" |
| M-02 | `home` | Home | Shortcuts, **offline queue badge**, last sync | → any tab |
| M-03 | `lookup` → `lookup/results` → `product/{id}` | Lookup | Camera scan (shelf/product) or type; results paged; product with locations | Unit → unit sheet (relocate, assign) |
| M-04 | `stow` | Stow | Scan shelf → scan units loop; vibration + sound per result | Done → M-02 |
| M-05 | `pick` | Pick | Scan unit → reason picker → confirm | Next scan ↺ |
| M-06 | `orders` | Orders to pick/ship | Requests with lines to pick (ACCEPTED with CIMH lines, APPROVED Pro Bono, PICKING) | Row → M-07 |
| M-07 | `orders/{id}/pick` | Pick order | Lines (CIMH/Pro Bono only) with progress; scan units; wrong unit → error chip | All picked → M-08 |
| M-08 | `orders/{id}/ship` | Ship | Carrier, tracking (camera scan of the label barcode), note, date | Ship → M-06 |
| M-09 | `create/product` | Create product | Form + photos (camera) | Save → product/{id} |
| M-10 | `create/location` | Create location | Site → location → shelves | Save ↺ |
| M-11 | `sync` | Sync queue | Queued scans with status; retry/discard failed | ↺ |

**Offline:**
- Scans are saved with a per-scan `Idempotency-Key` in Room and sent by WorkManager when the connection returns.
- The UI shows "queued" chips.
- A queued scan that the server rejects appears in M-11 with its error.

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
| 2 | S-03 | Add to request (qty; Pro Bono capped) | Toast; badge ↺ |
| 3 | S-07 | Review, adjust | S-08 |
| 4 | S-08 | Address, currency (paid lines), notes → Submit | S-09 (1 or 2 requests) |

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
| 2 | A-04 | Upload supplier PDFs, enter prices, (exchange rate) | Draft autosaved |
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
| S-01 | Legacy Home structure: hero carousel (owner's image, radar, AWS), logo band with the "Online Stores" sign-in card, "Radar Spares" and "Met-service Spares" rows. Hero files in `web/shop/src/assets/hero/` |
| S-02, S-04, S-06 | Legacy Inventory/NCI structure: title + search banner, type (Pro Bono: project) chips, Filters menu, product grid; search results on the same page (`/search` redirects to `/catalogue?q=`) |
| S-03 | Legacy InventoryItem structure: thumbnail strip + large photo left, one card right (name, availability, Pro Bono limit, description, details, units per pack, quantity, **Add to request disabled** until order-svc, P5). No price or serials |
| A-05, A-06, A-07 | Legacy SIA structure: list with grid/list toggle, search, filters, stock count; product page = photos + description left, Info card right, then tabs Details (edit, explicit Pro Bono choice), Images (upload, background removal, processing tiles, primary, remove), History (admins). "Create labels" comes with P4 |
| Shells | Legacy structure (owner rule 2026-11-07): SHOP = top bar on desktop, bottom navigation on phones, CIMH footer, no top bar on sign-in pages; SIA = one horizontal header with an Admin menu (no side drawer). Sign-in pages (both apps) = legacy split layout on the met-enclosure photo |
| A-01 | Legacy SIA Home structure: statement band, Radar / Hydro-Met spares cards, "What are you looking for today?" search, then the account counters |
| A-19 | Fees, email lists (active staff/admins), workflow, reference (departments; projects incl. inactive, rename, toggle) |
| S-10 | Empty state until order-svc (P5) |
| A-21, A-16, A-17, A-18, A-20 | As specified; A-16 suggests an organisation from the email domain, then the organisation text, and can create one in the dialog |
| Personal data (S-19, A-21, A-17) | "Your data" card: download (JSON) and ask to delete; A-17 marks and filters requests, exports and erases. The admin email for a request waits for notification-svc (P6) |
| A-01 | Identity counters only (pending approvals, unverified sign-ups) until order/inventory exist |
| **New:** `/mfa-setup` (SIA) | An admin without MFA lands here after login and can't use anything else (TR-AUTH-9). After confirming, the admin logs in again, because the old token predates MFA |
| **New:** `/staff-only` (SIA) | The "This app is for CIMH staff" screen of §2 |
| **SIA Mobile** M-01 + session (`mobile/sia`) | New app (id `bb.edu.cimh.sia`) next to the legacy one. Login with MFA code step, "staff only" for customers, admins without MFA sent to SIA web; refresh token sealed in the Android Keystore; app lock after 5 min (screen lock or strong biometric; no screen lock → signed out); HTTPS only with pinned Let's Encrypt roots. M-02 is a placeholder; M-03–M-11 come with P8. CI job `mobile` (unit, lint, debug + release build) |

Behaviour notes: the start-up session probe never shows "session ended" to an anonymous visitor (only a failed refresh during use does). Dev servers use ports 15173 (SHOP) and 15174 (SIA).
