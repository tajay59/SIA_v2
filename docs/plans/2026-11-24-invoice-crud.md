# Change plan: Invoices you can open, change and void (SIA A-03)

Date: 2026-11-24 · Status: **D1–D8 answered by the owner (2026-11-24); built the same day on branch `feat/invoice-crud` (not committed)** · Owner request 2026-11-24

**As built (differences from the plan below):** a stale revision is 409 `VERSION_CONFLICT` (the project's If-Match rule), not 412; automatic invoices charge the **signed total** (estimated shipping from the agreement, not parcel costs: the business rule "the signed total is what CIMH invoices"), while staff-built ones still start from parcel costs as before; an automatic invoice without a delivery number takes the suggested next one, else the request id; the dialog keeps its problems list (not `checkForm`); one record view serves customers (number, rev, fileId, date, total) and staff (+ lines, figures, revisions, `locked`, `source`); `voidedInvoices` on the staff view. mongomock can't check a unique index on an array, so the unit-test mock drops `unique` for indexes named `*_multikey` and a new real-Mongo test (`tests/integration/test_invoice_numbers.py`) covers it. Found on the way: label PDFs crashed on a barcode with a control character (reportlab QR encoder; Schemathesis) → refused with 422; the event JSON schemas had not been re-extracted since `number`/`notify` were added (regenerated).

Working plan, not part of the manual. When it is built, the affected docs and manual chapters change (§9) and this file records progress.

## 1. What the owner wants

On the SIA desk (`/requests`, the request beside the queue, and `/requests/[id]`), **Create invoice** and **Create commercial invoice** open the same `v-dialog` (`web/sia/src/components/InvoiceDialog.vue`) as today, but the dialog now **creates, reads, updates and deletes** the request's invoice instead of only creating new ones.

## 2. What exists today

| Today | Gap |
|---|---|
| `POST /requests/{id}/invoices` (document-svc) renders the legacy SIA template (`pdfs.built_invoice`), stores the PDF + a sidecar (`protected/meta/<fileId>.json`, keeps only `number`), publishes `document.generated` (`notify`), attaches the file to the request, audits `<kind>.created` | **What staff typed (lines, fees, discount, shipping, date) is thrown away**, so an invoice can't be reopened |
| No read endpoint for an invoice; the request's `files[]` is the only index | Nothing says which invoice is the current one |
| `DELETE /files/{id}` refuses generated documents (409 `GENERATED_DOCUMENT`) | Staff can't withdraw a wrong invoice |
| No number checks: any text, duplicates allowed | Two requests can carry invoice 2026-014 |
| document-svc also generates an **Invoice on `order.delivered`** (PAID; `pdfs.invoice`, a different layout) and a **commercial invoice per CIMH parcel leaving Barbados** (`order.shipment_recorded`) | Duplicates beside staff-built ones |
| `paymentStatus` DUE amount (`amountDue`) = agreement total, else legacy `total` | A discount or extra shipping on the invoice isn't what the customer is asked to pay |
| SHOP shows every invoice file as a Papers tile | Customers would see every old copy |

Note: document-svc owns **no collection** (TAD, ADR). The invoice record therefore lives in **order-svc** on the request (it already holds `invoice {number, date}` from Mark delivered and needs the total for `amountDue`); document-svc keeps rendering and storing PDFs.

## 3. Decisions (owner answers, 2026-11-24)

| # | Question | Answer |
|---|---|---|
| D1 | Invoices per kind per request | **One current invoice per kind** (`invoice`, `commercial_invoice`). The button opens it when it exists, otherwise a new one |
| D2 | Editing | **New revision, old kept**: same number, `rev n+1`, new PDF; customers see only the current one; old PDFs stay for staff + audit, marked replaced |
| D3 | Automatic invoices | **Skip when that kind already exists**; otherwise generate as today, registered as the current invoice and editable like a staff-built one. Pro Bono delivery note unchanged (not part of this) |
| D4 | Locking | **Read-only once marked paid**; after that only an **admin** can void it, with a reason |
| D5 | Second CIMH parcel leaving BB when a commercial invoice exists | **Nothing automatic**; A-03 Next step says which parcel lines it doesn't cover; staff add them (new revision) |
| D6 | Amount owed | **Current invoice total** (kind `invoice` only) replaces the agreement total in `amountDue` (SHOP outstanding payments, proof dialog, SIA Mark paid) |
| D7 | Numbers | **Typed; the builder suggests the next one** (last number of that kind + 1 on its trailing digits); a number used by another request's invoice of the same kind → 409 `INVOICE_NUMBER_TAKEN` |
| D8 | Emails | **Save: the same "Email to" ticks, both unticked by default** (email says "corrected invoice"); **delete: nobody** |

Assumptions (say if wrong): voided numbers stay taken (no reuse, accountants' rule); automatic invoices switch to the legacy SIA template (one layout for every invoice) and take Mark delivered's invoice number if given, else the suggested next number; a commercial invoice doesn't count toward `amountDue`.

## 4. Target design

### 4.1 Data: `orders.invoices` (order-svc, BSD §5.x)

```
invoices: {
  invoice?:            InvoiceRecord
  commercial_invoice?: InvoiceRecord
}
InvoiceRecord {
  number, numberKey (lower-cased, trimmed), rev (1…), fileId (current PDF),
  date, lines[{lineId?, description, qty, unitPrice}], fees, discount, shipping (Decimal128), total (Decimal128),
  source: STAFF | AUTO, createdBy/At, updatedBy/At,
  revisions[{rev, fileId, total, by, at}],          // every PDF ever issued, newest last
  voided?: {by, at, reason}                         // absent while current
}
```

- After a void, a new invoice of that kind replaces the record; the voided record moves to `invoicesVoided[]` (kept for staff + audit).
- Number uniqueness: every number ever issued on the request is in `invoiceNumbers: [{kind, numberKey}]` (added with `$addToSet` on create or a number change, never removed, voided ones included), with a **unique multikey index on (`invoiceNumbers.kind`, `invoiceNumbers.numberKey`)**: Mongo enforces it across requests, the code within one. A changed number on a revision adds the new one and keeps the old one taken. Real-Mongo integration test covers it (mongomock is loose with these indexes).
- Recording an invoice **does not bump the request `version`** (same rule as file attachments); the record has its own `rev` for If-Match.
- `files[]` entries of replaced PDFs get `replaced: true`; voided ones `voided: true` + reason. Customer views (`view()` for non-staff, `/internal/requests/{id}/access` downloads) hide both; staff see them in the invoice history.
- `$jsonSchema` (order-svc `schemas.py`): `invoices.*` requires `number`, `rev`, `fileId`, `total`.
- `amountDue` (`service.py` ~line 95): `invoices.invoice.total` when present and not voided, else agreement total, else legacy `total`. `SUMMARY_PROJECTION` adds `invoices.invoice.total`, `invoices.invoice.voided`.

### 4.2 API (contract first: `documents.openapi.yaml`, `orders.openapi.yaml`, authz matrix)

**document-svc (public, staff):**

| Method | Path | Does |
|---|---|---|
| GET | `/requests/{id}/invoices/{kind}` | Current record (form values, number, rev, fileId, revisions with file links, `locked`, `source`), 404 when none. `ETag: rev` |
| GET | `/requests/{id}/invoice-draft?kind=` | As today + `suggestedNumber` |
| POST | `/requests/{id}/invoice-preview` | Unchanged |
| POST | `/requests/{id}/invoices` | Create (rev 1). 409 `INVOICE_EXISTS` (one per kind), 409 `INVOICE_NUMBER_TAKEN` |
| PUT | `/requests/{id}/invoices/{kind}` | New revision. `If-Match: <rev>` required (428 without, 412 stale). 409 `INVOICE_LOCKED` once paid, `INVOICE_NUMBER_TAKEN` |
| DELETE | `/requests/{id}/invoices/{kind}` | Void, body `{reason}` (3–500). `If-Match`. Staff before paid; **admin only** once paid (403 otherwise). No email |

Flow for create/revise: render PDF → save file + sidecar (sidecar gains `rev`, `invoiceKind`) → **order-svc `PUT /internal/requests/{id}/invoices/{kind}`** (sync: checks one-per-kind / rev / lock / number, writes record + `files[]` entry + marks the previous file `replaced`, one conditional update) → on refusal the new file is removed and the 409/412 passed on → `document.generated` (`notify`, `number`, `rev`) → audit `invoice.created|revised`. Void: order-svc `DELETE /internal/…/invoices/{kind}` → sidecar `voided` → `document.deleted` (order-svc consumer is idempotent with the sync write) → audit `invoice.voided`.

**order-svc (internal, `require_services("document")`):** `PUT` / `DELETE /internal/requests/{id}/invoices/{kind}`, `GET /internal/invoice-numbers/next?kind=` (suggestion). `OrderRequest` (staff view) gains `invoices` (summary: number, rev, total, fileId, locked, source); customer view gets number + current fileId only.

New error codes in API README §4: `INVOICE_EXISTS`, `INVOICE_NUMBER_TAKEN`, `INVOICE_LOCKED`.

### 4.3 Automatic invoices (document-svc `consumer.py`)

- `order.delivered` (PAID): ask order-svc for the request; if `invoices.invoice` exists, do nothing (a voided one too: staff withdrew it on purpose, so nothing is regenerated behind them). Else render `built_invoice` from `invoice_draft` with the number (Mark delivered's `invoiceNumber`, else the suggestion; on `INVOICE_NUMBER_TAKEN` retry with the next), register as `source: AUTO`, rev 1. Event id → file id stays deterministic (redelivery = same file, order-svc create-only makes it a no-op).
- `order.shipment_recorded` (CIMH parcel, ship-to ≠ BB): same, kind `commercial_invoice`, lines = that parcel's CIMH lines; skipped when one exists (D5).
- `probono_invoice`: unchanged.

### 4.4 notification-svc

`document.generated` with `rev > 1`: subject/heading "Corrected invoice <number>" ("…commercial invoice…"), body says it replaces the earlier one. Ticks decide recipients as today. Nothing on void.

### 4.5 SIA: same dialog, CRUD (`InvoiceDialog.vue`, `RequestView.vue`)

**Buttons** (A-03 Next step card, `invoice-acts`): label follows state: **Create invoice** (none) · **Invoice 2026-014** (exists, opens for edit) · **View invoice** (locked, non-admin). Same for commercial. Shown from the same statuses as today.

**Dialog modes** (one component, `mode = new | edit | locked`, decided by `GET …/invoices/{kind}` on open; 404 → new from `invoice-draft`):

| | New (today) | Edit | Locked (paid) |
|---|---|---|---|
| Title | Create invoice | Invoice 2026-014 · rev 2 | Invoice 2026-014 · Paid |
| Head line | ref · organisation | + "Made automatically from the request" when `source: AUTO` | + "Read-only: the request is marked paid" |
| Number | suggested, editable | editable (re-checked) | read-only |
| Form | from the request | from the saved revision | read-only text, no fields |
| Preview | live | the saved PDF until a change, then live (marked Preview) | the saved PDF |
| Revisions | none | "Earlier copies" row under the head: rev 1 · person · date · Open (in `FilePreviewDialog`) | same |
| Undo changes | back to the request | back to the saved revision | none |
| Footer left | Email to ☑ ☑ | Email to ☐ ☐ ("corrected invoice") | none |
| Footer right | Back · Create | **Delete invoice…** (danger, apart) · Back · **Save changes** (disabled only when nothing changed, forms rule) | Back · (admin) **Void invoice…** |

- Delete/Void asks first in a `v-dialog` (shared `ReasonDialog`: reason required, says "The customer no longer sees it and is not emailed. Number 2026-014 stays used."). After it the dialog closes and the button reads Create invoice again.
- 409 `INVOICE_EXISTS` (someone created it meanwhile) / 412: reload the record, keep the typed values beside a notice "Changed by <name> at <time>; review and save again". 409 `INVOICE_NUMBER_TAKEN`: number field marked with the message, focus to it.
- Validation moves to `v-form` rules + `checkForm` (forms rule; the dialog still uses the old problems list).
- Golden-ratio dialog system kept (`dialog-system` memory): plain head split φ : 1, 8 px fields.
- **Next step note** (D5): when a CIMH parcel to a non-BB address has lines not on the current commercial invoice: "Commercial invoice 2026-014 doesn't cover parcel 2 · Edit it".
- Files panel on A-03: replaced/voided invoices fold under the current one ("2 earlier copies").

### 4.6 SHOP

S-11 Papers: one tile per kind (current PDF, "Invoice 2026-014", "rev 2" when > 1); replaced/voided never listed. Outstanding payments + proof dialog amounts follow `amountDue` (no code change beyond the summary field; check copy "On the invoice").

### 4.7 Existing data (order-svc start-up upgrade `invoices`, idempotent)

Per request, the newest non-deleted file of kind `invoice` / `commercial_invoice` becomes `invoices.<kind>` with `rev 1`, `source: AUTO` (or STAFF when the file's uploader is a person), `fileId`, `number` from `invoice.number` (Mark delivered) or the file name, **no lines** (`lines: null`, `total: null`). Older files of the same kind → `replaced`. Opening such an invoice in SIA: the form is seeded from `invoice-draft` + the number, with a note "This copy was made before invoices kept their lines; saving issues rev 2". `amountDue` ignores a null total. `invoiceNumbers` is filled the same way; a duplicate number found by the upgrade is logged (request ids) and only the first request keeps it in `invoiceNumbers` (the others take a number when staff next save them), so the unique index can always be built. Check staging first (38 legacy invoices + any built since #52) with a read-only count.

## 5. Tests

- order-svc: record create / revise / void, one per kind, rev conflict, lock after Mark paid, admin void after paid, number uniqueness (real-Mongo integration test), `amountDue` from invoice total, customer view hides replaced/voided, upgrade (idempotent, duplicates logged).
- document-svc: create → internal refusal removes the new file; PUT renders rev 2 and marks rev 1 replaced; DELETE; consumer skips when one exists, AUTO registration, number retry; Schemathesis + generated authz matrix for the new routes.
- notification-svc: corrected-invoice wording; no mail on void.
- Web: unit tests for mode selection and the next-number suggestion; Playwright J-06 extended: create invoice → reopen (form filled, saved PDF shown) → change a price → Save (rev 2, earlier copy listed) → Delete with reason → button back to Create; J-04: SHOP shows only the current invoice and the outstanding amount equals the invoice total; axe on the edit, locked and delete dialogs; chromium + 360 px.

## 6. Delivery

One branch `feat/invoice-crud`, one PR: contract → order-svc (record, internal routes, amountDue, upgrade) → document-svc (routes, consumer) → notification-svc → generated web client → SIA dialog → SHOP tiles → tests → docs. Dev images rebuilt (order, document, notification) before Playwright.

## 7. Risks

- **Two writers** (document-svc file + order-svc record): handled by order-svc deciding first and document-svc removing the new file on refusal; a crash between them leaves an orphan PDF that nothing lists (harmless; sidecar sweep could clean it later).
- **Staging data**: the upgrade turns 38+ legacy invoices into records without lines and may meet duplicate numbers (logged; first one keeps its number). Mitigation: run the read-only duplicate check on staging before merging; dump first.
- `amountDue` changing for requests already DUE on staging (customers see a different amount after deploy if a staff-built invoice differs from the signed total). Expected per D6; mention to staff.

## 8. Out of scope

Credit notes; invoices for other kinds (Pro Bono delivery note, CIMH quote); editing from SIA Mobile; invoice numbering per year/prefix rules beyond "trailing digits + 1".

## 9. Docs to update (with the PR)

`docs/api/documents.openapi.yaml`, `orders.openapi.yaml`, `events.asyncapi.yaml` (`rev` on `document.generated`), API README (codes, endpoint catalogue), BSD (`orders.invoices`, file flags, retention: invoices kept), APD A-03 (dialog modes, buttons, next-step note) + S-11 Papers, PRD (D* story for invoice edits), TAD §4.5 (document↔order internal calls), SECURITY (void after paid = admin), TEST_STRATEGY (J-06 steps), SIA `DESIGN.md` (dialog modes), manual ch. 4/10/11 + rebuild.
