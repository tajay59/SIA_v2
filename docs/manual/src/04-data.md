# 4. Data

[← Architecture](03-architecture.md) · [Manual home](README.md) · [Next: Workflows →](05-workflows.md)

Source: [BSD](../BSD.md) (field-level definitions, the source of truth), [TAD §6](../TAD.md), [TRD §4.3](../TRD.md).

## 4.1 Where data lives

| Data | Store | Location | Backed up |
|---|---|---|---|
| Business data | MongoDB replica set `rs0` (mongo1 host primary, mongo2/3 on Raspberry Pi 5) | database **`inventory`** | Nightly `mongodump` from Pi B → restic → other CIMH site |
| Files | Docker volume | `/srv/sia-data` | Nightly restic → other CIMH site |
| Sessions, revocations, limits, idempotency, processed events, locks, cache | Redis (AOF) | main host | No (rebuildable; users log in again) |
| Events in transit | Kafka | main host | No (MongoDB is the source of truth) |
| Metrics | Prometheus | main host | No |

**File layout:**

```
/srv/sia-data/
  protected/   orders/<orderId>/<uuid>.<ext>   labels/<uuid>.pdf        (document-svc + X-Accel-Redirect only)
  public/      products/<productId>/<uuid>.webp (+@800, @320)   shelves/<barcode>.png   (served by nginx)
```

## 4.2 Collection ownership and access

![Data ownership](images/08-data-ownership.svg)

| Collection | Owner | DB user | Rights | Today | At 1M users |
|---|---|---|---|---|---|
| `accounts` | identity | `svc_identity` | find, insert, update | 65 | 1M |
| `temp` | identity | `svc_identity` | find, insert, update, remove | 0 | ~10k (TTL) |
| `organisations` ✚ | identity | `svc_identity` | find, insert, update | — | ~5k |
| `auditlog` ✚ | identity | `svc_identity` | find, **insert** (update only to anonymise purged accounts) | — | +2M/yr |
| `product` | catalog | `svc_catalog` | find, insert, update | 83 | 2M |
| `xuser` (view) | catalog | `svc_catalog` | find | view | — |
| `misc` | catalog | `svc_catalog` | find, insert, update | 12 | ~5k |
| `storage` | inventory | `svc_inventory` | find, insert, update | 697 | 30M |
| `history` | inventory | `svc_inventory` | find, insert | 860 | +5M/yr |
| `orders` | order | `svc_order` | find, insert, update | 39 | +1.5M/yr |
| `products` | — | — | **dropped** (empty legacy collection) | 0 | — |

Other database users:
- `svc_backup`: read only.
- `svc_migrate`: used for the migration only, then disabled.
- `admin_ops`: for people doing administration; never used by an app.

### Who sees what

| Data | Customer (`user`) | `staff` | `admin` |
|---|---|---|---|
| Own account | Read/write (email change needs re-verification) | Read | Read/write |
| Other accounts | ✗ | Name, email, organisation, role, status | All except secrets |
| Product public fields | Sellable only (via `xuser`) | Read | Read |
| Product `cost`, `threshold`, `sn`, `sn1` | ✗ | Read/write | Read/write |
| Stock | "In stock / on request" only | Exact counts, units, history | Same |
| Requests | Own **and** same organisation (read); own (act) | All | All |
| Quote amounts, exchange rate | On their requests | Read/write | Read/write |
| Supplier names, purchase orders | ✗ | Read/write | Read/write |
| Audit log | ✗ | ✗ | Read |

`passwordHash`, `mfa.*` and `failedLogins` never leave identity-svc.

## 4.3 Shared types and ids

| Type | Definition |
|---|---|
| `Money` | Decimal128, 2 decimals, **BBD** for catalogue cost (never float) |
| `Currency` | `BBD` or `USD` (one per request) |
| `Timestamp` | UTC BSON Date, shown in America/Barbados |
| `Address` | line1, line2?, city, parish?, country (ISO-2), zip?, organisation?, attention? |
| `Actor` | `{ id, name, role }`: who did something |
| `StatusChange` | `{ from?, to, by: Actor, at, reason? }` |
| `OutboxEvent` | `{ eventId (ULID), type, version, occurredAt, correlationId, actorId?, payload, attempts }` |

**Id prefixes:**

| Prefix | Entity |
|---|---|
| `USR` | Accounts (legacy ids kept) |
| `ORG` | Organisations |
| `ORD` | Requests (legacy ids kept) |
| `CRT` | Carts |
| `QTE` | Quotes |
| `FIL` | Files |
| `AUD` | Audit log entries |
| `TMP` | Temporary codes |

Products, units, sites, locations and shelves keep their legacy barcode formats.

## 4.4 Collections at a glance

### `accounts`
`id` (unique) · `email` (unique, case-insensitive) · `passwordHash` (Argon2id; legacy hash upgraded at next login) · `firstname`, `lastname`, `phone` · `role` · **`status`** · `isCimh` · `organisationText` (typed) → **`organisationId`** (set at approval) · `department`, `country` · `addresses[]` (max 10) · `defaults{site, location, shelf}` (staff) · `verifiedAt`, `approvedBy/At`, `rejection` · `statusHistory[]` · `failedLogins` · `mfa` · `approvalReminderAt` · `erasureRequestedAt` (the person asked to be deleted) · `deletedAt` (purge or erasure in progress) · `outbox[]`.
Removed: `cart` (moves to `orders`), `emailconfirmed`, `registered`, `timestamp`, `password`.
Rule: an `ACTIVE` non-CIMH account must have an `organisationId`.

### `temp`
Verification and reset codes: `kind`, `accountId`, **`codeHash`** (for checking), `codeEnc` (an AES-GCM sealed copy that notification-svc can claim **once** to send the email, then removed), `newEmail` (email changes only), `attempts` (max 5), `sentCount` (max 3 per hour), `expireAt` (+15 min, **TTL index**).

### `organisations` ✚
`id`, `name` (unique, case-insensitive), `country`, `type`, `emailDomains[]` (to suggest a match at approval), `aliases[]` (typed names that map to this organisation), `mergedInto?`, `active`.

### `auditlog` ✚ (can only be added to)
`id` (= source eventId, so duplicates are impossible), `at`, `actor`, `action`, `entity{type,id}`, `from/to`, `reason`, `ip`, `correlationId`. The service user can insert and read only. Kept indefinitely; personal data is removed when an account is deleted.

### `product`
`id` (unique) · `name`, `description`, `details`, `make`, `modelname`, `modelnumber` · **`type`** codes `MET, RAD, EQUIP, SUPP, MISC, PRO` · `department`, `project` · **`sellable` → bool** · **`probono` bool (required at creation)** · `probonoMaxPerRequest?` · `cost` (Money, staff only) · `threshold`, `unitquantity`, `weight`, `dimension`, `sn`, `sn1` · `keywords[]` · `images[]{fileId, url, w, h, primary}` · `inStock`, `stockCount`, `stockAt` (derived from stock events; an older event never overwrites a newer one) · `active` (soft delete).
Search: a **text index** (name 10, modelnumber 8, keywords 5, make 3, modelname 3) plus prefix indexes on `sn`, `sn1`, `modelnumber`. Browsing is sorted by name (indexes end in `name, id` for cursor paging); every filter combination the screens use (customer: all / type / type + department; staff: active or "show inactive", with or without type) has its own index, and CI checks with `explain` that no catalogue read scans the collection (TR-DATA-5).

### `xuser` (view)
`product` filtered to `sellable: true, active: true`, projecting **only public fields**, so `cost` and serials can never reach a customer. catalog-svc creates the view at start-up from the same field list its public API uses.

### `misc` (reference data, now with a `kind` field)

| `kind` | Holds |
|---|---|
| `departments` | Department list |
| `types` | Type codes and labels |
| `projects` | One document per project |
| `fees` | Admin fee used in CIMH quotes |
| `emailLists` | Lists: registration, order, invoice, cancellation, lowStock |
| `site` / `location` / `shelf` | **One document per shelf** (split out of the old `shelves[]` arrays) |
| `counter` | Product number sequence |
| `settings` | `quoteValidityDays` 30, `quoteReminderDays` 3, `approvalReminderHours` 48, `purgeAfterDays` 90 |

### `storage` (one document per physical unit)
`barcode` (**unique**) · `product` · `serial` · location (`site/location/shelf` + names) · `stowed`, `stowby`, `stowdate` · `picked`, `pickedby`, `pickeddate`, `pickedreason` · `orderid` (picked for) · ✚ **`reservedFor`** (reserved for) · ✚ `reservedAt` · ✚ `assignedTo` (issued to a person; off the shelf) · `images[]` · `updatedAt`.
**Available** = `stowed && !picked && reservedFor == null`. Unit barcodes keep the legacy `<productId>_<8 hex>` form.
New key index: `{ product, stowed, picked, reservedFor }`; `reservedFor`, `orderid` and `assignedTo` have small partial indexes. Seven of today's nine indexes are dropped once usage checks confirm they're covered.

### `history` (movement log, added to and never edited)
`id` (unit barcode) · `operation` (stow, pick, relocate, assign, unassign, reserve, release, adjust) · `reason` · location after the move · `from` (for relocate) · `user` · ✚ `accountId` (assign/unassign) · `orderId` · `date`.

### ✚ `stock` (counts per product, inventory-svc)
`id` (= product id) · `productName`, `type`, `threshold`, `active` (copied from catalog events) · `available`, `reserved`, `picked`, `assigned` · `low` · `outbox[]`.
Updated **in the same transaction** as every scan, with counts recomputed from `storage`, so counts always reconcile with units and history. It carries inventory's outbox, so stock events are keyed by product id. Low = threshold > 0 and available ≤ threshold; `stock.low` is sent when it turns true.

### `orders` (carts and requests)

| Group | Fields |
|---|---|
| Common | `id` (`ORD…`/`CRT…`), `type` (`PAID`/`PROBONO`/null), **`status`**, `customer`, `customerSnapshot`, `organisationId`, `lines[]`, `currency`, `shipTo`, `notes`, `version`, `createdAt`, `updatedAt`, `submittedAt`, `history[]`, `outbox[]` |
| Line | `lineId`, `productId`, `product` (details copied at submission), `qty`, `choice` (CIMH/SUPPLIER), `cimhAvailable`, `reservation{status, units[]}`, `picked[]` |
| Supplier quotes | `quotes[]`: `id`, `version`, `supplier`, `lines{unitPrice, total}`, `total`, `fileIds`, `expiresAt` (+30 d), `sentAt/By`. **Every version is kept** |
| CIMH quote | `cimhQuote`: `lines{unitCostBBD, unitPrice, total}`, **`exchangeRate`** (required for USD), `total`, `fileId` |
| Quote state | `quoteVersion`, `quoteExpiresAt`, **`adminFee`** (once per request, in the request currency), `quoteDraft` (staff) |
| Decision | `acceptance{quoteVersion, choices[], by, at, ip}` or `decline{by, at, reason}` |
| Fulfilment | `purchaseOrders[]`, `approval` / `rejection` (PROBONO), `shipping{carrier FEDEX/DHL/HAND, tracking (required unless HAND), cost, date, by}`, `invoice{…}`, `files[]`, `cancellation{by, at, reason, auto}` |

Key rules:
- One cart per user (only carts carry `cartOf`; a sparse unique index).
- Accounts with `isCimh` can't have a cart or requests.
- A mixed cart is split into one PAID and one Pro Bono request.
- Status changes must follow the allowed flows, and each is a conditional update.

## 4.5 Relationships

![Entity relationships](images/09-entity-relationships.svg)

| From | Field | To | Checked by |
|---|---|---|---|
| `accounts` | `organisationId` | `organisations.id` | identity |
| `orders` | `customer` | `accounts.id` | order, at submission |
| `orders` | `organisationId` | `organisations.id` | copied at submission |
| `orders.lines` | `productId` | `product.id` | order → catalog, at submission |
| `storage` | `product` | `product.id` | inventory |
| `storage` | `reservedFor` / `orderid` | `orders.id` | inventory, via events |
| `storage` | `site/location/shelf` | `misc` | inventory, via the catalog API |
| `history` | `id` | `storage.barcode` | inventory |

There are no joins or foreign keys across services. If a referenced record disappears, the copy saved on the request is shown instead.

## 4.6 Consistency rules

| Situation | How it's kept consistent |
|---|---|
| Status change | Conditional update that includes the expected current `status` → `409 Conflict` if it has already changed |
| Several units reserved together | Multi-document **transaction** ([Chapter 5.5](05-workflows.md#55-stock-reservation)) |
| Other services must react | Outbox → Kafka → idempotent consumers (eventually consistent, usually < 1 s) |
| Derived values (`inStock`) | Updated by events; display only; decisions always ask the owner |

Writes use `w: majority` + `retryWrites`. Reads come from the `primary`, except reports and backups, which read from secondaries.

## 4.7 Validation

Every collection has a `$jsonSchema` validator generated from the service's Pydantic models. It is set to `moderate`/`warn` during migration, then switched to `strict`/`error` once the migration is signed off.

## 4.8 Retention

| Data | Kept for |
|---|---|
| `temp` codes | 15 min (TTL index) |
| Unverified accounts | 24 h → `EXPIRED` |
| Rejected / expired accounts | 90 days, then deleted (audit entries have personal data removed) |
| Carts | Emptied after **180 days** of inactivity |
| Requests, quotes, files | Indefinitely (financial records) |
| Audit log, movement history | Indefinitely (archived yearly if very large) |
| Kafka events | 7–30 days |
| Backups | 30 daily + 12 monthly (pending confirmation) |
| Container logs | 10 × 50 MB per container |

**Right of access:** people download their own data from their profile (staff appear by role only); admins can export anyone's. Each export is audited.

**Right to erasure:** the person asks from their profile (password required), and an admin erases the account with a reason. The name, contact details, addresses and sign-in are removed, sessions end, the person's audit entries lose name and IP, and `user.deleted` tells other services to replace the personal data on requests with `[deleted]` (open requests are cancelled). The financial fields and the audit trail are kept. The 90-day purge of rejected and expired accounts uses the same steps.

## 4.9 Migration from the legacy data

| Legacy | v2 |
|---|---|
| `accounts.password` | Argon2id at next login |
| 65 existing accounts (56 user, 6 staff, 3 admin) | `ACTIVE`; `emailconfirmed` → `verifiedAt`; customers linked to an organisation during review |
| `accounts.cart[]` | `orders` document with `status: CART` (ids and quantities only) |
| `product.sellable` `yes` / `no` / `probono` | `sellable` bool + **`probono` bool** (`probono` → sellable + Pro Bono; 3 products today) |
| `product.probono` | Set from legacy `sellable = "probono"`; **new products get the flag at creation** |
| `product.cost` float | Decimal128 |
| `misc` | `kind` added; shelves split into one document each |
| `orders.cart` + `ncicart` | `lines[]`; split into PAID + Pro Bono requests if both exist |
| `orders.complete` / `cancelled` / other | `DELIVERED` / `CANCELLED` / **`SUBMITTED`** |
| `storage` | + `reservedFor: null` (no duplicate barcodes in the reference DB) |
| `orders.shipping.method` (free text) | `FedEx` → `FEDEX`, `DHL` → `DHL`, `Hand delivered…` → `HAND` (text kept in `shipping.note`) |
| `orders.billedto`, `total`, `shippingestimate` | `billTo` kept; legacy totals kept read-only under `legacy.*` |
| `history.operation` `orderpick` | `pick` with `orderId` |
| SQLite tokens | Not migrated (everyone logs in again) |
| `products` (empty) | Dropped |

**Reference data:** the database `inventory` on **`172.16.0.203`** (MongoDB 8.0.26) holds the real data. The local `127.0.0.1` copy is test data. The current `xuser` view shows customers types `MET, RAD, PRO, EQUIP` with `sellable` `yes` or `probono`.
