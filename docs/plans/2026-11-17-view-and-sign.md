# Change plan: "View and sign" paid request flow

Date: 2026-11-17 · Status: **decisions D1–D7 accepted as recommended (owner, 2026-11-17); PR A built 2026-11-18 (branch `feat/view-and-sign`, not committed); PR B next** · Owner request 2026-11-17

**PR A as built (differences from the plan below):** the data move runs at order-svc start-up (`order_svc/upgrade.py`, idempotent, logs the request ids staff must re-send) instead of a `tools/migrate` script, so dev, CI, staging and the cut-over all get it without a manual step; `/internal/availability` takes an optional `orderId` (a revised quote re-checks the stock it already holds); inventory swaps a revised quote's reservation in one transaction (one result event, unchanged need = no-op) instead of release-then-reserve; the separate "agreement ready" email was dropped (the quote email is the one "view and sign" email). Playwright J-02…J-07 were updated but not run locally (Docker Desktop failed to start).

Working plan, not part of the manual. When a slice is built, the affected docs and manual chapters change (§8) and this file records progress.

## 1. The flow the owner wants

1. The customer submits a request for *n* items.
2. Staff decide the source of every line: **in CIMH stock** → CIMH stock quote (generated); **not in stock** → staff get quotes from suppliers and upload them to the request.
3. Staff send the quote. The customer sees the supplier quotes, the CIMH stock quote, the price of every line, the estimated shipping and the **order total**.
4. The customer downloads **one agreement PDF**: every item, its price, estimated shipping, total, signature line.
5. The customer either **signs and uploads it** (commits to pay) or **cancels**. Nothing to choose: **"View and sign, or cancel"**.
6. After the signed copy is uploaded (and staff check it), staff place orders with the suppliers; **suppliers ship straight to the customer**.
7. Staff pick and ship the in-stock items.
8. Staff enter tracking for each shipment; the customer's request page shows **one tracking link per shipment**: CIMH's shipment and each supplier's direct shipment.

## 2. What is wrong today

| Today (built in P5/P6) | Needed |
|---|---|
| A line can carry a CIMH offer **and** a supplier offer; the customer chooses per line (`POST /agreement` with `choices`) | Staff fix one source per line when sending the quote |
| Agreement PDF is generated only after the customer chooses (`QUOTED → AWAITING_AGREEMENT`, event `order.agreement_requested`) | Agreement PDF is generated with the quote (`order.quoted` / `order.quote_revised`) |
| Status `AWAITING_AGREEMENT`; "Change choices" goes back to `QUOTED` | No separate status: `QUOTED` = quote out, waiting for the signed copy |
| SHOP S-12 "Choose and sign" (3-step stepper, radio per line) | S-12 **"View and sign"**: check, download, upload signed copy; or cancel |
| Quote builder shows a **range** of totals (customer picks) | One exact total |
| No shipping estimate on the quote or the agreement (legacy had `shippingestimate`) | Estimated shipping on the quote, the agreement and the total |
| One `shipping` record per request (carrier, tracking, one link) | **Several shipments**: one for CIMH stock, one per supplier, each with its own tracking link |
| Carriers FedEx, DHL, hand delivery only | Suppliers ship with whatever carrier they use (see D5) |
| Stock reserved at acceptance | See D2: the signed PDF now promises the stock |

Already right and kept: supplier quote files are visible to the customer (any file on a request they can see); admin fee once per request; every quote in BBD with supplier USD converted at a staff rate; 30-day validity + 3-day reminder; staff check the signature before purchase orders (O6a); Pro Bono flow; mixed-cart split; no payments, no carrier APIs.

## 3. Decisions for the owner (recommendation first)

| # | Question | Recommended | Alternative |
|---|---|---|---|
| D1 | A line only partly in stock (want 5, hold 3) | **Whole line from a supplier** (today's "full quantity" rule) | Split the line: 3 from stock + 2 from a supplier (new line-splitting, partial reservations; much more work) |
| D2 | When is CIMH stock reserved? | **When the quote is sent**: the signed PDF promises those units; held for the quote's 30 days, released on cancel / decline / expiry / a revision that drops the line | At acceptance (today): a unit can be taken by someone else after the customer signed; staff then revise and the customer signs again |
| D3 | Shipping estimate granularity | **One estimate per source**: CIMH stock (BBD) + each supplier (in the supplier's currency, converted at its rate); 0.00 allowed, but must be entered | One figure for the whole request |
| D4 | Is the signed total final? | **Yes**: the invoice charges the signed total; shipping costs recorded on shipments are for CIMH's records | Invoice uses actual shipping costs (the customer pays a number they never signed) |
| D5 | Carriers | **FedEx, DHL, UPS, Hand delivery, Other** (Other = carrier name + a tracking link staff paste, https only). Still no carrier APIs | Keep FedEx, DHL, Hand (supplier shipments by UPS etc. get no link) |
| D6 | Customer sees supplier names (on lines and shipments) | **Yes**: they already hold the supplier's quote document. BSD access matrix changes | "Shipped directly by the supplier" without a name |
| D7 | Statuses | **Drop `AWAITING_AGREEMENT`**, keep every other name. The SHOP "Cancel request" while `QUOTED` is the existing `decline` (reason kept) | Keep `AWAITING_AGREEMENT` as the name of the waiting state and drop `QUOTED` (more renames, same behaviour) |

Not asked, decided by the plan: the customer cannot drop lines or accept part of a quote (they ask staff to revise, or cancel); staff signature check stays (O6a); a rejected signature gives the customer at least 7 more days (`quoteExpiresAt = max(current, now + 7 d)`).

## 4. Target design (assumes the recommended answers)

### 4.1 Paid state machine (`tests/transitions/request_paid.yaml` = `order_svc/domain.py`)

```
SUBMITTED  → QUOTING     start-quoting     staff
SUBMITTED  → CANCELLED   cancel            requester|staff|admin
QUOTING    → QUOTED      send-quote        staff      guard: every line has one source and a price; a shipping estimate per source
QUOTING    → CANCELLED   cancel            requester|staff|admin
QUOTED     → QUOTED      send-quote        staff      quote revised; earlier agreement void
QUOTED     → ACCEPTED    accept            requester|admin   guard: signed agreement uploaded for THIS quote version, quote live
QUOTED     → DECLINED    decline           requester|admin   SHOP "Cancel request" (reason)
QUOTED     → CANCELLED   expire            system     30 days
ACCEPTED   → QUOTED      reject-agreement  staff      signature not acceptable; customer uploads again (≥ 7 days left)
ACCEPTED   → PURCHASING  purchase          staff      guard: agreementVerified; a PO for every supplier line (none needed if all stock)
ACCEPTED   → CANCELLED   cancel            staff|admin
DECLINED   → CANCELLED   close             system
PURCHASING → SHIPPED     ship              staff      automatic when the last line is covered by a shipment
SHIPPED    → DELIVERED   deliver           staff
```

Removed: `QUOTED → AWAITING_AGREEMENT` (agreement), `AWAITING_AGREEMENT → QUOTED` (change-choices), `AWAITING_AGREEMENT → ACCEPTED/CANCELLED`, `ACCEPTED → AWAITING_AGREEMENT`. `QUOTE_LIVE = ("QUOTED",)`. Pro Bono table unchanged except that `PICKING → SHIPPED` also happens through shipments (§4.3).

### 4.2 Data (`orders`, BSD §5 + validators §7)

| Field | Change |
|---|---|
| `status` | enum loses `AWAITING_AGREEMENT` |
| `lines[].choice` | **renamed `lines[].source`** (`CIMH`\|`SUPPLIER`), set at **send-quote** (was acceptance); new `lines[].supplier` (name, null for CIMH) |
| `quoteDraft.supplierQuotes[]` | + `shippingEstimate` (supplier's currency); a line may sit in **one** supplier quote **or** CIMH, never both |
| `quoteDraft.cimh` | + `shippingEstimate` (BBD) |
| `quotes[]` | + `shippingEstimate` (BBD), + `sourceShippingEstimate` (USD when converted) |
| `cimhQuote` | + `shippingEstimate` (BBD) |
| `agreement` | created at **send-quote** for that version: `{ quoteVersion, total, fileId, signedFileId, verified, rejections }`; `total` = lines + shipping estimates + admin fee. `choices` removed |
| `acceptance.choices` | no longer written (old values left in place) |
| `shipping` (one) | **replaced by `shipments[]`**: `{ id: "SHP…", source, supplier?, lineIds[], carrier: FEDEX\|DHL\|UPS\|HAND\|OTHER, carrierName?, tracking?, trackingUrl? (OTHER only), date, cost?, note?, by, at, notified }` |
| `reservation` per line | set at send-quote (D2) instead of acceptance |

Access matrix (D6): supplier names on lines, quotes and shipments readable by the customer and same-org users. Purchase orders stay staff-only.

### 4.3 API (`docs/api/orders.openapi.yaml`, regenerate `packages/web-api/src/generated/orders.ts`)

- **Removed** `POST /requests/{id}/agreement` and `POST /requests/{id}/ship`.
- `PUT /quote-draft`: shipping estimates; 422 `LINE_SOURCE_CONFLICT` when a line is in two places.
- `POST /send-quote`: 422 `QUOTE_INCOMPLETE` (line without source/price), `SHIPPING_ESTIMATE_REQUIRED`.
- `POST /accept` from `QUOTED`; same body (`quoteVersion`, `signedAgreementFileId`); 409 `QUOTE_OUTDATED` when the signed file was uploaded for an earlier version (document-svc stamps `quoteVersion` on `signed_agreement` uploads from the access check).
- **New** `POST /requests/{id}/shipments` (staff, If-Match): `{ source, supplier?, lineIds, carrier, carrierName?, tracking?, trackingUrl?, date, cost?, note?, notifyCustomer }`. Paid from `PURCHASING`, Pro Bono from `APPROVED`/`PICKING`. Rules: lines not yet shipped (`LINE_ALREADY_SHIPPED`); CIMH/Pro Bono lines fully picked (`PICKING_INCOMPLETE`); supplier lines have a PO; tracking unless HAND (`TRACKING_REQUIRED`); OTHER needs a name + https link (`TRACKING_URL_INVALID`). Covering the last line moves the request to `SHIPPED` in the same conditional update.
- **New** `PATCH /requests/{id}/shipments/{shipmentId}` (staff, If-Match): fix carrier/tracking/link/date/cost/note; history entry; optional re-notify.
- Request view: `lines[].source/supplier`, shipping estimates, `agreement.total`, `shipments[]` with `trackingUrl` (templates for FedEx/DHL/UPS, staff link for OTHER), `allowedActions`: customer `accept`, `decline` while `QUOTED`; staff `ship` while lines are unshipped.

### 4.4 Events (`events.asyncapi.yaml`, topic `order.events`, no ACL change)

- `order.quoted` and `order.quote_revised`: same payload: `quoteVersion, expiresAt, total, lines[{lineId, productId, qty, source, supplier?}], shippingEstimates`.
- `order.agreement_requested`: **removed**.
- `order.accepted`: `lines[].source` (was `choice`).
- **New** `order.shipment_recorded` / `order.shipment_updated`: `orderId, customer, shipmentId, source, supplier?, lineIds, carrier, carrierName?, tracking?, trackingUrl?, notifyCustomer`.
- `order.shipped` stays (all lines shipped), no longer emailed.
- `document.generated` for `agreement` / `cimh_quote`: + `quoteVersion`, so a late PDF for v1 never lands on v2.
- Roll-out: consumers read `source ?? choice` and skip a stray `order.agreement_requested` until the old events are drained.

### 4.5 Services

| Service | Change |
|---|---|
| **order-svc** | `domain.py` table + `QUOTE_LIVE`; `save_draft` exclusivity + estimates; `send_quote` sets `lines[].source/supplier`, converts supplier shipping, builds `agreement` + total, emits the full payload; `agreement()` and `change-choices` deleted; `accept` from QUOTED with the version check; `reject_agreement` → QUOTED, +7 days; `purchase_orders` unchanged apart from `source`; `ship` → `record_shipment` / `update_shipment`; `pick` keys on `source`; `view`/`allowed_actions`; consumer attaches `agreement.fileId` only for the matching `quoteVersion`; jobs; `schemas.py` validators; `forget_person` covers `shipments` |
| **document-svc** | Consumer: `order.quoted`/`quote_revised` → **agreement** (always) + CIMH quote (CIMH lines); `order.shipment_recorded` with source CIMH and ship-to ≠ BB → commercial invoice for that shipment's lines; `order.delivered` → invoice. `pdfs.agreement` rewritten: lines grouped "From CIMH stock" / "From <supplier>, shipped directly to you", unit + total, estimated shipping per group, admin fee, **Total (BBD)**, USD rates, valid-until, terms, signature block (signature, name, position/organisation, date). Invoice = signed total (D4). CIMH quote wording on reservation (D2). `_may_upload`: `signed_agreement` while `QUOTED`, stamped with `quoteVersion` |
| **inventory-svc** | D2: reserve CIMH lines on `order.quoted`; on `order.quote_revised` reserve added CIMH lines and release dropped ones; release on `order.declined`, `order.expired`, `order.cancelled`; **not** on `order.agreement_rejected` (quote still live); `order.accepted` reserves nothing. Reads `source ?? choice` |
| **notification-svc** | `quoted` / `quote_revised`: total + "view and sign, or cancel" link to S-12; `agreement_rejected`: upload again; **new** `shipment_recorded` (one email per shipment: items, "sent by CIMH" / "sent directly by <supplier>", carrier, tracking link); `shipment_updated` only when re-notify; `order.shipped` route removed; staff email on `signed_agreement` upload kept |

### 4.6 Screens

**SHOP**
- **S-11** `RequestSheet`: QUOTED well "Your quote is ready · Total BBD x · valid until …" with **View and sign** + **Cancel request**; Quote section = one consolidated `QuoteTable` (line, source tag, unit, total; shipping per source; admin fee; total; USD notes), no option tiles; Files: supplier quotes, CIMH quote, agreement; **Delivery** lists shipments (source, items, carrier, date, **Track ↗**) and "Not shipped yet" for the rest. Path: Sent · Quote · Signed · Ordered · Shipped · Delivered.
- **S-12** `/requests/[id]/agreement` → **View and sign**: 1 Check the quote (summary + files) · 2 Download the agreement · 3 Upload the signed copy → **Send signed agreement** (upload + accept). **Cancel request** (reason, confirm). Choice radios, "Confirm choices", "Change choices" removed.
- S-10 "Waiting for you" = QUOTED; `web-app/orders.ts` labels; `HowRequestingWorks` + home copy (We quote → View and sign → We ship, with tracking).
- Shared `QuoteTable`: `picked`/choice mode removed, shipping rows added (also used by SIA).

**SIA**
- **A-04** quote builder: a line belongs to one tab (giving it a supplier price takes it out of CIMH stock and the reverse, with a note); fully-in-stock lines start in CIMH stock; **Estimated shipping** per supplier tab (supplier's currency) and on CIMH stock (BBD); footer shows the exact total (range removed); Send confirm states the total and that the customer gets the agreement to sign.
- **A-03** `RequestView`: Next step per status: QUOTED "Waiting for <customer> to sign"; ACCEPTED "Check the signed agreement" (open file → Reject signature / Record purchase orders with "signature checked"); PURCHASING: pick CIMH lines, **Shipments** panel ("Record shipment" per open source, list with Edit); SHIPPED: Mark delivered.
- `ShipDialog` → **ShipmentDialog**: source (CIMH stock / supplier), its unshipped lines preselected, carrier tiles (FedEx, DHL, UPS, Hand, Other + name + link), tracking, date, cost, email switch.
- Desk / dashboard / `request-queue.ts` / `work-counts.ts` / `web-ui/status.ts`: `AWAITING_AGREEMENT` gone; "Waiting for signature" = QUOTED, "Signature to check" = ACCEPTED, "To ship" = PURCHASING with unshipped lines.

**Mobile** (`OrdersApi.kt`, `OrdersScreens.kt`): M-08 Ship records a CIMH shipment of the picked lines via `/shipments` (UPS/Other added); `choice` → `source`. Supplier shipments are recorded on the web only.

## 5. Data migration

New `tools/migrate/view_and_sign.py`: idempotent, prints counts only (real data), `--dry-run` default.

1. `lines[].choice` → `lines[].source` (all requests).
2. `AWAITING_AGREEMENT` → `QUOTED`, history entry (`by: system`, reason "flow change: view and sign"); line sources from the customer's choices.
3. Open quotes (`QUOTED`) where a line still has two offers: **listed by id** for staff to revise and re-send (new agreement). Same for every request moved in step 2 (their agreement PDF shows "Your choices").
4. `shipping` → `shipments[0]` covering all lines (source CIMH for Pro Bono; from the line sources when they agree, else null = "Shipment").
5. Then validators in `strict` again.

Order: dry run against a local copy of the staging dump → staging: dump to `/opt/sia-staging/backups/`, deploy, run, check counts. order-svc reads old shapes (`choice`, `AWAITING_AGREEMENT`, `shipping`) until the script has run, so the deploy has no broken window; the shims go after cut-over. `MIGRATION_PLAN` M05 mapping: legacy `shipping` → `shipments[0]`; legacy `shippingestimate` stays read-only under `legacy`.

## 6. Tests

- order-svc: transitions YAML (generated 409s follow), paid flow rewrite (exclusive sources, shipping maths incl. USD, accept from QUOTED, outdated signed file, reject → QUOTED + 7 days, revision voids agreement), shipments (partial, auto-SHIPPED, picking/PO guards, OTHER link, edit), authz matrix for the 2 new endpoints, Schemathesis, migration script on fixtures.
- document-svc: agreement PDF text (every line, shipping, total, signature line), commercial invoice per CIMH shipment, upload state + version stamp.
- inventory-svc: reservation trigger per D2, `source ?? choice`. notification-svc: shipment email with link, no `order.shipped` mail.
- Playwright `orders.spec.ts`: J-05 (one source per line + shipping), **J-03 rewritten** (view, download, sign, upload; no choosing), J-06 (verify, POs, pick, CIMH shipment + supplier shipment), J-04 (both tracking links), J-07 (Pro Bono shipment); axe on S-12 + ShipmentDialog; 360 px. `tools/e2e/order_smoke.py`. Mobile JVM test for the shipment body.

## 7. Delivery

Two PRs, each complete on its own (backend + web + tests + docs), because the required `e2e` check runs J-02…J-07 against the whole stack:

| PR | Branch | Contents |
|---|---|---|
| A | `feat/view-and-sign` | §4.1, data/API/events for quote + agreement + reservations, order/document/inventory/notification changes, A-04, A-03 (up to purchase orders), S-11 quote part, S-12, QuoteTable, migration steps 1–3, J-03/J-05 |
| B | `feat/shipments` | `shipments[]`, the two endpoints, `/ship` removed, ShipmentDialog, S-11 Delivery, mobile M-08, commercial invoice per shipment, shipment emails, migration step 4, J-06/J-04/J-07 |

Each PR: contract first (validate with `openapi-spec-validator` / `npx @asyncapi/cli validate`), then services, then screens, then docs + manual rebuild + CLAUDE.md. Staging migration runs right after PR A deploys (and step 4 after PR B).

## 8. Docs to update (with the PR that changes them)

PRD O3, O5, O5a, O6, O6a, O7, O8, O9, O10, O11 + §6 journey 2 · TAD §5 (order/document/inventory/notification rows), §7.2 sequence + state diagram, events list · BSD orders fields, validators §7, access matrix (D6), legacy mapping · API README (catalogue, error codes) · APD S-10, S-11, S-12, A-02, A-03, A-04, M-08, J-03 ("Quote → view → sign → accepted"), J-05, J-06, emails §7 · Design Brief status chips · Test Strategy RTM · Migration Plan M05 · manual ch. 04, 05, 10, 11, 13 · diagrams 11 (paid status), 14 (paid flow), 15 (stock reservation), 25 (journey quote acceptance) via `_generate.py` · CLAUDE.md business rules ("Acceptance = signed agreement", "CIMH stock quote … customer picks").

## 9. Risks

- **Stock held for unaccepted quotes** (D2): up to 30 days. Acceptable at CIMH's volume (39 requests so far); the low-stock board shows it as Reserved.
- **Signed copy of an old version**: blocked by the `quoteVersion` stamp on the upload.
- **Real data on staging**: dump first; counts only; requests needing a re-sent quote listed for staff.
- **Events in flight at deploy**: tolerant consumers (§4.4).
- **Installed SIA Mobile builds** still call `/ship`: only internal APKs exist; PR B ships the new APK.

## 10. Out of scope

Payments; carrier APIs or live tracking status; customer dropping lines or accepting part of a quote; splitting a line between stock and a supplier (D1); e-signatures (the signature stays a signed scan or photo).
