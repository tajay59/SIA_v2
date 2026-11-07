# Data Migration Plan: CIMH Stores Platform v2

| | |
|---|---|
| **Document status** | DRAFT |
| **Document owner** | T. Edwards |
| **Related documents** | [BSD §9](BSD.md) (field mapping summary) · [TAD §9.5](TAD.md) · [SECURITY](SECURITY.md) · [Manual](manual/index.html) |
| **Source of truth for data** | Reference DB `inventory` on **172.16.0.203** (MongoDB 8.0.26, standalone) |
| **Last updated** | 2026-11-06 |

---

## 1. Purpose

How existing data moves from the legacy Flask system into v2 **without loss**: what moves, how each field is transformed, how it is checked, the dry-run schedule, the cut-over steps and how to roll back.

## 2. Source and target

| | Source (legacy) | Target (v2) |
|---|---|---|
| Database | `inventory` on 172.16.0.203, standalone | `inventory` on replica set `rs0` (host + 2 Pis) |
| Schema | Legacy (BSD "⟲/✖" fields) | BSD §5 |
| Files | `SIA/app/` on the legacy host: `invoices/`, `uploads/`, `tempquotations/`, `productImages/`, `qrcodes/` | `/srv/sia-data/{protected,public}` with UUID names |
| Login tokens | SQLite `database.db` (`Tokenlist`) | Not migrated: everyone logs in again |

### 2.1 Source inventory (counted 2026-11-06)

| Collection | Docs | Notes |
|---|---|---|
| `accounts` | 65 | 56 user / 6 staff / 3 admin; 9 `@cimh.edu.bb`; carts embedded |
| `product` | 83 | MET 49, EQUIP 19, RAD 12, PRO 3; sellable yes 48 / no 32 / **probono 3** |
| `storage` | 697 | 484 stowed, 213 picked; no duplicate barcodes |
| `orders` | 39 | 36 with `cart`, 3 with `ncicart`; complete 7, cancelled 1, paid 8; `shipping.method` free text |
| `history` | 860 | stow 639, orderpick 189, pick 32 |
| `misc` | 12 | departments, emails, fees, types, 2 project, 2 site, 4 location (with `shelves[]`) |
| `temp` | 0 | — |
| `products` | 0 | Empty legacy collection: **dropped** |
| `xuser` | view | Recreated (BSD §5.6) |
| **Total** | **~1,756 documents** | Plus files on disk (to be counted in dry run 1) |

## 3. Strategy

**One-time cut-over in a short maintenance window**, not a long parallel run.

| Option | Verdict |
|---|---|
| Run legacy and v2 in parallel on two databases with continuous sync | **Rejected:** the legacy app writes the old schema; two-way sync for status, carts and stock is complex and error-prone for ~1.8k documents |
| Point legacy Flask at the new schema | **Rejected:** would need rewriting legacy code |
| **Freeze → migrate → verify → switch → keep legacy read-only for rollback** | **Chosen:** small data (minutes to migrate), clean rollback, one source of truth at all times |

Consequence for [TAD §9.5](TAD.md) (strangler): the **front-end/route switch** can still be staged during testing on staging, but **production data moves once**; at cut-over all `/api/*` routes go to v2 together, and `/sia/api/*` is switched off (read-only fallback kept for 30 days).

```
 Legacy (live) ──freeze──► final dump ──► migrate (scripts) ──► verify ──► go / no-go
                                                                      │
                                     go ──► switch nginx to v2 ──► smoke tests ──► open
                                  no-go ──► unfreeze legacy (nothing lost)
```

## 4. Tooling

| Item | Design |
|---|---|
| Runner | `tools/migrate/` Python package, run as a one-off container (`docker compose run migrate …`) |
| Steps | Ordered, **idempotent** scripts `m001_…py` … each with `plan()` (dry-run report), `apply()`, `verify()` |
| Modes | `--dry-run` (read source, write a report + would-be documents to a scratch DB) · `--apply` (write target) · `--verify` |
| Credentials | Source: **read-only** user `svc_migrate_ro` on 172.16.0.203 (create it; do not use `cimhAdmin`). Target: `svc_migrate` (`readWrite` on `inventory`), disabled after sign-off |
| Reports | `reports/migration/<run-id>/`: counts, mapping table of every free-text value, warnings, PII-free (ids only) |
| Validators | Target `$jsonSchema` at `moderate`/`warn` during apply (BSD §7), switched to `strict` after verify |
| Re-runnable | Target is wiped and rebuilt from the dump on every run until sign-off; never mutates the source |

## 5. Mapping by collection

Field-level targets are in the [BSD](BSD.md). Order of execution follows dependencies.

### M01 `misc` (→ catalog reference data)
| Legacy | v2 |
|---|---|
| `id:"departments"` | `kind:"departments"`, `values[]` |
| `id:"types"` (dict) | `kind:"types"`, `values:[{key: MET…, label}]` (key = product code) |
| `id:"project"` (2 docs) | one `kind:"projects"` doc each: `id:"project:<code>"`, `code`, `name`, `active:true` |
| `id:"fees"` | `kind:"fees"`; `fee` int → `Money` (BBD) |
| `id:"emails"` (`registration/order/invoice/cancellation[]`) | `kind:"emailLists"`; members keep `account` → `accountId`; add empty `lowStock[]` |
| site docs (2) | `kind:"site"`, `id`=`barcode`, `name`, `country`, `address`, `active:true` |
| location docs (4) with `shelves[]` | `kind:"location"` (4 docs) **+ one `kind:"shelf"` doc per array entry** (`barcode`, `number` (Int64→int), `site`, `location`) |
| — | `kind:"settings"` with defaults (30 / 3 / 48 / 90 / 180) · `kind:"counter"` `product` = max(`product.number`) |

### M02 `organisations` (new) and `accounts`
1. **Organisations** are created from distinct values found in `orders.shipto.organization` / `billedto.organization` and account data, normalised (trim, case-fold), **reviewed by an admin** in the dry-run report (merge duplicates, set country). CIMH itself becomes an organisation for `@cimh.edu.bb` accounts.
2. **Accounts:**

| Legacy | v2 |
|---|---|
| `id`, `email` (lower-cased), `firstname`, `lastname`, `role`, `department`, `image` | same |
| `password` (Werkzeug hash) | `legacyPasswordHash`; `passwordHash` empty until first login (TRD TR-AUTH-7 upgrade) |
| `emailconfirmed:true`, `registered` | `verifiedAt` = `registered` parsed (fallback `timestamp`) |
| — | `status: ACTIVE` (all 65); `isCimh` from email domain; `organisationId` from step 1 (customers without a match → **listed for admin to assign before go-live**) |
| `address[]` | `addresses[]` (structured where parseable; else `line1` = original text) |
| `site/sitename/location/locationname/shelf/shelfnumber` | `defaults{site,location,shelf}` (staff/admin only; dropped for customers) |
| `cart[]` | → M06 carts; removed from account |
| `timestamp` | `createdAt` |
| — | `statusHistory:[{to:"ACTIVE", by:"svc:migrate", at:<cut-over>, reason:"Migrated from legacy"}]`, `failedLogins:{count:0}`, `outbox:[]`, `version:1` |

### M03 `product`
| Legacy | v2 |
|---|---|
| `sellable:"yes"` | `sellable:true, probono:false` |
| `sellable:"no"` | `sellable:false, probono:false` |
| `sellable:"probono"` | `sellable:true, probono:true` (3 products) |
| `cost` float | `Money` Decimal128 (2 dp, BBD) |
| `images[]` (file names) | `images[]{fileId,url,w,h,primary}`: files copied by M08; first = primary |
| `keywords[]` | lower-cased, de-duplicated |
| other fields | unchanged; add `active:true`, `inStock` (computed from storage), `createdAt/updatedAt` = cut-over, `outbox:[]`, `version:1` |

### M04 `storage`
Unchanged fields + `reservedFor:null`, `reservedAt:null`, `assignedTo` (**mapped from legacy self-stow data**: units stowed to a person rather than a shelf become `assignedTo: <accountId>`; the exact field rule is listed in the DR-1 report), `updatedAt`. Indexes rebuilt per BSD §5.8 (`barcode` **unique**).

### M05 `history`
| Legacy `operation` | v2 |
|---|---|
| `stow` | `stow` |
| `pick` | `pick` |
| `orderpick` | `pick` + `orderId` (from the matching `orders.cart[].picked` / `ncicart[].picked` entry by barcode and date) |

### M06 Carts (from `accounts.cart`)
Each non-empty `accounts.cart` → one `orders` document `id: CRT…`, `status: CART`, `customer`, `lines[]{productId, qty: count}` (product snapshots **not** copied from the legacy cart; rebuilt from `product`). Lines for inactive/unknown products are dropped and listed in the report.

### M07 `orders` (requests)
| Legacy | v2 |
|---|---|
| `cart[]` and `ncicart[]` both non-empty | **Split:** original id keeps the PAID lines (`type: PAID`); new id `ORD<hex>` for the Pro Bono lines (`type: PROBONO`); both get a `history` note linking the sibling |
| only `cart[]` | `type: PAID` |
| only `ncicart[]` | `type: PROBONO` |
| `cart[]/ncicart[]` `{id, count, picked[]}` | `lines[]{lineId, productId: id, qty: count, picked[]}` + product snapshot from `product`; legacy `cart[].cost` kept as `legacy.lineCost` |
| `complete:true` | `status: DELIVERED` |
| `cancelled:true` | `status: CANCELLED` (`cancellation.reason:"Cancelled in legacy system"`) |
| otherwise | **`status: SUBMITTED`** (decision); `legacy.paid` kept for staff reference |
| `customer` | same; `customerSnapshot` from legacy `firstname/lastname` + account email |
| — | `organisationId` from the customer's account (M02) |
| `ordered` | `submittedAt`, `createdAt` |
| `shipto` / `billedto` | `shipTo` / `billTo` (`organization` → `organisation`, `office` → `attention`) |
| `shipping.method` free text | `"FedEx"` → `FEDEX` · `"DHL"` → `DHL` · `"Hand delivered…"` → `HAND` (+ `note` = original text) · empty → no `shipping` · other → `HAND` + `note`, listed in report |
| `shipping.tracking/cost/date` | `tracking`, `cost` (Money), `date` (string dates parsed; unparseable → report) |
| `shipping.cost1`, `total`, `shippingestimate` | `legacy.shippingCost1`, `legacy.total`, `legacy.shippingEstimate` (read-only) |
| `invoice{number…, date}` | `invoice` (date string → Date) |
| `files[]{file,name,type}` | `files[]{id, kind, name, mime, size, sha256, path}`: file copied by M08; `type` mapped to `kind` (`inv`→`invoice`, `ci`→`commercial_invoice`, other→`upload`) |
| — | `currency: "BBD"` for PAID (legacy prices are BBD), `null` for PROBONO; `version:1`; `history:[{to:<status>, by:"svc:migrate", reason:"Migrated from legacy"}]`; `outbox:[]` |

> Legacy orders have **no quotes or agreements**. SUBMITTED paid orders will be quoted in v2 normally (customers notified, see §9).

### M08 Files
| Source | Target | Rule |
|---|---|---|
| `SIA/app/productImages/*` | `public/products/<productId>/<uuid>.webp` (+@800, @320) | Re-encoded through the media pipeline (EXIF stripped) |
| `SIA/app/invoices/*.pdf`, `uploads/*`, `tempquotations/*` referenced by `orders.files[]` or by order id in the file name | `protected/orders/<orderId>/<uuid>.pdf` | SHA-256 recorded; **ClamAV scan** first; unreferenced files listed (not migrated unless an admin says so) |
| `SIA/app/qrcodes/*` | — | **Not migrated**: regenerated from shelf/site barcodes |
| `database.db`, `Spares.db`, logs | — | Not migrated; archived with the legacy backup |

### M09 Indexes, views, validators
Create every index in BSD §5 (incl. unique `accounts.email`, `storage.barcode`, cart partial index, text index); recreate `xuser` view (BSD §5.6); apply validators (`moderate` → `strict` after verify); drop `products`.

## 6. Verification (automated, every run)

| Check | Rule |
|---|---|
| Counts | accounts 65 → 65; product 83 → 83; storage 697 → 697; history 860 → 860; orders 39 → 39 + (number of split orders, expected 0–3) requests + carts = non-empty legacy carts; misc 12 → 12 − 4 locations-with-arrays + 4 locations + N shelves + settings + counter |
| Sums | Σ line qty per legacy order = Σ v2 line qty (incl. split sibling); count of picked units unchanged; stowed/picked unit counts unchanged (484/213) |
| References | every `storage.product` exists in `product`; every `orders.customer` exists in `accounts`; every `orders.lines.productId` exists; every `files[].id` has a file on disk with matching SHA-256; every non-CIMH ACTIVE customer has `organisationId` |
| Schema | 0 validator warnings on all collections before switching to `strict` |
| Enumerations | `status`, `type`, `carrier`, `sellable/probono` only take allowed values |
| Uniqueness | `accounts.email`, `storage.barcode`, one CART per customer |
| Spot checks (manual) | 10 random orders, 10 products, 10 units, 5 accounts compared side by side legacy UI vs v2 UI by a staff member |
| Login | Test accounts (one per role) log in with their **existing** password (legacy hash → Argon2id upgrade works) |

Go/no-go requires **all automated checks green** and the manual spot-check signed off.

## 7. Dry runs

| Run | When | Environment | Goal | Exit criteria |
|---|---|---|---|---|
| DR-1 | When M01–M09 first complete | Local / CI against a dump | Scripts run end-to-end; report reviewed | All scripts succeed; report lists every free-text mapping |
| DR-2 | After organisation review and fixes | Staging (main host, `sia-staging`) | Full rehearsal incl. files and ClamAV; v2 UI checks | All checks green; spot-check signed; timing measured |
| DR-3 | ≤ 7 days before cut-over | Staging, fresh dump | Final rehearsal with the exact runbook (§8) | Duration ≤ 45 min; zero manual fixes needed |

Each dry run produces a **Migration Dry-run Report** (Documentation Index #19).

## 8. Cut-over runbook (production)

Window: a weekday **after 17:00 Barbados time**, 2 hours reserved (expected ~45 min). Customers and staff notified 5 working days ahead.

| T | Step | Owner |
|---|---|---|
| T-5 d | Announce maintenance window (email to all ACTIVE accounts + SHOP banner) | Admin |
| T-1 d | v2 production stack deployed and healthy with an **empty** database; DR-3 signed | Tech lead |
| T-0:00 | Enable **maintenance mode** on legacy nginx (SHOP/SIA show a maintenance page; `/sia/api` returns 503) | Ops |
| T-0:05 | Stop Flask (gunicorn); confirm no writes (`db.currentOp()`, last `history.date`) | Ops |
| T-0:10 | `mongodump` of source (read-only user) + copy legacy file folders; checksum both | Ops |
| T-0:20 | Run `migrate --apply` (M01–M09) into production `rs0` | Tech lead |
| T-0:35 | Run `migrate --verify`; review report | Tech lead |
| T-0:45 | Manual spot-check (staff member) + role logins | Staff + admin |
| T-0:55 | **Go / no-go** decision | Owner |
| T-1:00 | Switch nginx to v2 (`/api/*`, new SHOP/SIA builds); remove legacy routes; enable validators `strict` | Ops |
| T-1:05 | Smoke tests: login per role, browse, submit test request (then cancel), stow/pick a test unit, download a migrated invoice | QA |
| T-1:15 | Lift maintenance; post "We've upgraded" notice | Admin |
| T+1 h | Watch alerts (errors, logins, 403/404), keep legacy read-only VM/containers stopped but intact | Ops |

## 9. Communication

| Audience | Message | When |
|---|---|---|
| All accounts | Maintenance window; afterwards **log in again** (same password); new look | T-5 d and T+0 |
| Customers with SUBMITTED paid orders | Your request will now receive a formal quote; you'll accept by signing an agreement | T+1 d |
| Staff | Training on SIA v2 + mobile app update (install from internal distribution) before T-0 | T-7 d |
| Admins | Review the organisation list and unassigned customers (dry-run report) | Before DR-2 |

## 10. Rollback

| Situation | Action | Data loss |
|---|---|---|
| No-go at T-0:55 | Discard target DB; restart Flask; remove maintenance mode | None (source never modified) |
| Critical defect within **48 h** after go-live | Put v2 in maintenance; **export v2 changes made since cut-over** (new accounts, requests, scans, from `auditlog`/`history`/`orders` by `createdAt` ≥ cut-over) to a CSV report; restart legacy from its untouched DB; staff re-key the exported changes in legacy | Only re-keying effort; nothing lost |
| After 48 h | Fix forward (no rollback) | — |

Legacy database and files are kept **read-only for 30 days**, then archived (encrypted, restic) and the legacy server decommissioned.

## 11. Risks

| # | Risk | Mitigation |
|---|---|---|
| MR1 | Free-text values (organisations, shipping method, dates, addresses) mapped wrongly | Every distinct value listed in the dry-run report and reviewed before DR-2 |
| MR2 | Customers without a clear organisation block go-live (ACTIVE requires `organisationId`) | Admin review before DR-2; fallback organisation "Unassigned (review)" is **not** allowed, so list must be complete |
| MR3 | Legacy password hashes not verifiable in v2 | Test with real staff accounts in DR-2; fallback: forced password reset email |
| MR4 | Missing or orphaned files on the legacy server | File inventory in DR-1; missing files reported per order; unreferenced files reviewed |
| MR5 | Writes during the freeze (cron jobs, mobile app queue) | Stop Flask entirely; mobile app v1 shows maintenance (503); verify last write time |
| MR6 | Legacy currency | Resolved: BBD |

## 12. Questions

| # | Question | Outcome |
|---|---|---|
| 1 | Are legacy order amounts in BBD? | **Resolved:** yes. Paid orders get `currency: "BBD"`. |
| 2 | Status of the 8 orders marked `paid: true` but not complete? | **Resolved:** `SUBMITTED` (with `legacy.paid` kept for staff). |
| 3 | Where are the legacy files? | **Resolved:** in `SIA/app/` (`invoices/`, `uploads/`, `tempquotations/`, `productImages/`, `qrcodes/`) on the legacy host. |
| 4 | Can self-stow data be mapped to `assignedTo`? | **Resolved:** yes. M04 maps it (rule confirmed in DR-1). |
