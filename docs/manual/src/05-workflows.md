# 5. Workflows

[← Data](04-data.md) · [Manual home](README.md) · [Next: Security →](06-security.md)

Source: [PRD §5](../PRD.md), [TAD §7](../TAD.md).

## 5.1 Registration and approval

![Registration and approval](images/13-registration-flow.svg)

1. The registrant signs up with name, email, password (≥ 12 characters, checked against known-breached passwords), organisation (free text), department, country and phone.
2. A 6-digit code is emailed (valid 15 min, 5 attempts, at most 3 resends per hour). The `user.registered` event carries only a reference; notification-svc claims the code from identity-svc once and sends it.
3. **`@cimh.edu.bb`** → `ACTIVE` immediately (but cannot request items). **Everyone else** → `PENDING_APPROVAL`; admins on the `registration` email list are notified.
4. An admin approves (linking an organisation and choosing a role) or denies (a reason is required). The user is emailed either way.
5. If an account has been waiting more than 48 h, admins get a reminder.

Account statuses: see [Chapter 2.2](02-users-roles-apps.md#22-account-life-cycle).

## 5.2 Submitting a request

1. A customer (an active member-organisation `user`) adds items to the cart. Pro Bono items are capped at their per-request maximum.
2. At submission the customer chooses **BBD or USD** and a shipping address.
3. order-svc checks the cart with catalog-svc and saves a copy of each product's details on the request.
4. A cart with **both** paid and Pro Bono items is **split into two requests**.
5. `order.submitted` is published, and staff and the customer are emailed.

## 5.3 Paid request: quote to delivery

![Paid request flow](images/14-paid-request-flow.svg)

| Step | Who | What happens | Status |
|---|---|---|---|
| 1 | Staff | Start quoting. order-svc asks inventory-svc whether the **full** quantity of each line is in stock | `QUOTING` |
| 2 | System | Lines fully in stock get a **CIMH option** priced at catalogue cost + admin fee (staff enter the exchange rate if the request is in USD) | |
| 3 | Staff | Upload supplier quote PDFs and enter supplier amounts; send the quote (expires in 30 days) | `QUOTED` |
| 4 | System | Generates the CIMH quote PDF; emails the customer; sends a reminder 3 days before expiry | |
| 5 | Customer | Chooses **CIMH or SUPPLIER for each line** that has both (or declines with a reason) | `AWAITING_AGREEMENT` / `DECLINED` → `CANCELLED` |
| 6 | System | Generates the **payment agreement PDF** with the total of the chosen quotes | |
| 7 | Customer | **Downloads the agreement, signs it, uploads the signed copy** → accepted (commitment to pay). They can still change choices before uploading | `ACCEPTED` |
| 8 | System | Reserves the CIMH-chosen units. If stock has run out, staff must requote that line | |
| 9 | Staff | Checks the signature. If it's not acceptable, rejects it with a reason and the customer uploads again | `AWAITING_AGREEMENT` |
| 10 | Staff | Confirms the agreement is verified and records purchase-order numbers for each supplier | `PURCHASING` |
| 11 | Staff | Picks the **CIMH-stock lines only**. Supplier items are shipped **direct** to the customer and never enter stock | |
| 12 | Staff | Records carrier (FedEx, DHL, Hand delivered) and tracking number; the customer may be emailed | `SHIPPED` |
| 13 | Staff | Marks delivered; the invoice is generated | `DELIVERED` |

Acceptance records **who, when, from which IP, the choice for each line and the signed agreement file**. Only the latest quote version can be accepted; earlier versions are kept.

### Paid request status flow

![Paid request status flow](images/11-paid-request-status.svg)

A request can be cancelled up to and including `ACCEPTED` (which releases any reserved stock). Once purchasing starts, it can't be cancelled.

## 5.4 Pro Bono request

![Pro Bono request status flow](images/12-probono-request-status.svg)

No quote and no customer acceptance step. Staff approve the request against stock (which reserves the units), then pick, ship and deliver. Staff can reject it with a reason. Cancelling an approved request releases its stock.

## 5.5 Stock reservation

![Stock reservation](images/15-stock-reservation.svg)

- Runs inside inventory-svc as a **MongoDB transaction** (possible because MongoDB runs as a replica set).
- A unit is only ever claimed if `reservedFor` is empty. If the number of units claimed is short, the whole transaction is rolled back.
- Temporary transaction conflicts are retried up to 3 times.
- Release is `reservedFor: orderId → null`, which is safe to repeat.

## 5.6 Stow and pick

![Stow and pick](images/16-stow-pick-flow.svg)

Every scan is sent with an **Idempotency-Key**, so a mobile scan replayed from the offline queue is never applied twice. Each stow or pick updates the unit, adds a `history` record and publishes events that update stock levels (and trigger low-stock emails).

## 5.7 Protected file download

![Protected download](images/17-protected-download.svg)

document-svc checks the caller's permission: staff and admins always have access; a customer must own the request or belong to the same organisation, which document-svc confirms with order-svc. If allowed, nginx streams the file from a hidden internal location. Files are never served from a path the user supplies.

## 5.8 Notifications (emails)

| Event | Recipients |
|---|---|
| Account registered | User (verification code) |
| Account verified (needs approval) | Admins (`registration` list) + user ("awaiting approval") |
| Account approved / rejected / suspended | User |
| Approval pending > 48 h | Admins |
| Request submitted | Staff (`order` list) + customer |
| Quote ready / reminder (3 days before expiry) / expired | Customer |
| Agreement ready to download and sign | Customer |
| Signed agreement uploaded (quote accepted) / quote declined | Staff |
| Signature rejected (upload again) | Customer |
| Reservation failed (stock gone) | Staff |
| Shipped (with carrier + tracking) / delivered (with invoice) | Customer |
| Cancelled | Customer + staff (`cancellation` list) |
| Low stock | Staff |

All emails are sent by notification-svc through the CIMH mail server, at most once per event, with retries and the DLQ if sending keeps failing.
