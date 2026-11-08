# Product Requirements Document — CIMH Stores Platform (SHOP · SIA · SIA Mobile)

| | |
|---|---|
| **Target release** | TBD (v2.0, microservices platform) |
| **Epic** | CIMH Stores Platform v2 |
| **Document status** | DRAFT |
| **Document owner** | T. Edwards |
| **Designer** | TBD |
| **Tech lead** | TBD |
| **Technical writers** | TBD |
| **QA** | TBD |
| **Last updated** | 2026-11-06 |

---

## 1. Objective

Replace the current Flask app and its two Vue frontends with a secure, scalable platform that can serve up to **1,000,000 registered users**. The platform has three clients:

- **SHOP** (`store.cimh.edu.bb`): a web storefront where approved member-state organisations browse the catalogue and submit **order requests**.
- **SIA** (`sia.cimh.edu.bb`): the Stock Inventory App, a web app staff use to manage products, storage, stock movements, requests, quotes, purchasing and shipping.
- **SIA Mobile**: a native Android app staff use for scanning on the warehouse floor (lookup, stow, pick, pick orders, shipping).

Customers do not pay online. Paid items are **quoted by staff from suppliers and confirmed by the customer** before purchase. **Pro Bono items** are supplied free from CIMH stock.

## 2. Success metrics

| Goal | Metric |
|---|---|
| Scale | Supports 1M registered users; p95 API latency < 300 ms for catalogue and search at peak load |
| Availability | 99.5% monthly uptime for SHOP and SIA |
| Security | Zero critical findings in pre-launch security review; every endpoint authenticated and authorised by role and ownership |
| Request turnaround | Median time from `SUBMITTED` to `QUOTED` ≤ 5 business days |
| Fulfilment accuracy | 0 oversold stock units; 100% of picks recorded against a request |
| Account control | 100% of new accounts reviewed by an admin before first login |

## 3. Background and strategic fit

CIMH holds instruments, spares and supplies (met, radar, equipment, supplies, misc, projects) and supplies them to member-state meteorological and hydrological organisations. The current system works, but it:

- Has critical security flaws: code injection through `eval`, unauthenticated routes, and users able to read other users' data by changing an id (IDOR).
- Cannot scale: it opens a new database connection per query, keeps login tokens in SQLite, and stores files on a single host's disk.
- Models orders as "buy now", which does not match how CIMH actually sources items, through supplier quotes.
- Lets anyone with a verified email use the store.

v2 changes the order model to a **request → quote → accept → purchase → ship** workflow, adds **admin approval of accounts**, and rebuilds the backend as microservices that communicate over Kafka. It keeps MongoDB and the existing data (reference DB: **83 products, 697 storage units, 39 orders, 65 accounts**).

## 4. Assumptions

1. All three clients use one shared set of microservices and **one MongoDB deployment: a 3-member replica set**: the primary on the main host, plus a secondary on each of **two Raspberry Pis**, with one `inventory` database (layout in section 7). **Each service owns its own collections** and never reads or writes another service's collections directly.
2. **Existing collection names are kept.** Ownership:

   | Service | Collections it owns |
   |---|---|
   | identity-svc | `accounts`, `temp`, **`organisations`** (new), **`auditlog`** (new) |
   | catalog-svc | `product`, `xuser` (view), `misc` (reference data: sites/shelves are read through inventory-svc's API) |
   | inventory-svc | `storage`, `history`, `stock` (new) |
   | order-svc | `orders` |
   | document-svc | file metadata stored on `orders.files[]` through order-svc's API (no collection of its own) |
   | notification-svc | none (reads email lists from catalog-svc's API) |

   `auditlog` is written **only** by identity-svc's audit consumer, which reads audit events from all services over Kafka. Other services never write to it directly.
3. The replica set makes **MongoDB multi-document transactions available**. They are used where one change spans several documents, such as reserving several `storage` units for a request. Outgoing Kafka events are stored on the changed document ("embedded outbox") in the same write, then published by a relay.
4. Stack: FastAPI services, MongoDB replica set, Kafka (KRaft), Redis, nginx, local file storage on a Docker volume, deployed with **Docker Compose only** (one Compose project per host). Frontends (SHOP and SIA web) are **Vue 3 + TypeScript + Vuetify 4**. Full stack in the [TRD](TRD.md).
5. **Roles:** exactly three: `admin`, `staff`, `user` (customer). One account has one role.
6. Customers belong to **member-state organisations**. They type the organisation name in free text, and the admin links the account to a standard organisation record when approving it. **Users in the same organisation can see each other's requests.**
7. **`@cimh.edu.bb` accounts skip admin approval:** they become `ACTIVE` as soon as their email is verified. They **cannot submit order requests**; an admin assigns them `staff` or `admin` for SIA access.
8. No online payments. Payment and supplier purchasing happen offline; the system records the status, documents and references.
9. Customers never see prices on product pages. Prices appear only on quotes and invoices. **Currencies: BBD or USD. Each request uses one currency only, never both.**
10. Existing data is migrated: the 5 existing accounts become `ACTIVE`; **all existing open orders become `SUBMITTED`**; completed orders become `DELIVERED`; cancelled orders become `CANCELLED`.
11. Email is the only notification channel at launch.
12. Times are stored in UTC and shown in America/Barbados (UTC−4).

## 5. Requirements

Priority: **Must** = launch blocker · **Should** = launch target · **Could** = post-launch.

### 5.1 Accounts and access (identity-svc)

| # | Title | User story | Priority | Notes |
|---|---|---|---|---|
| A1 | Register | As a member-state employee, I want to create an account with name, email, password, organisation (free text), department, country and phone, so that I can request items. | Must | Replaces `/register`. Password policy: minimum 12 characters, checked against known-breached passwords. |
| A2 | Verify email | As a registrant, I want to confirm my email with a 6-digit code, so that CIMH knows the address is mine. | Must | Code expires after 15 min (resend limit 3/hour). Account becomes `EXPIRED` if not verified within 24 h. |
| A3 | Admin approval | As an admin, I want to approve or deny verified accounts, so that only genuine member-state staff can request items. | Must | Status flow: `PENDING_VERIFICATION → PENDING_APPROVAL → ACTIVE / REJECTED`. A reason is required to deny. Admins can approve or deny several at once. When approving, the admin links the account to a standard organisation (pick existing or create new). **`@cimh.edu.bb` emails skip this step** (`PENDING_VERIFICATION → ACTIVE`). |
| A3a | Organisations | As an admin, I want to maintain a list of organisations (name, country, email domains) and merge duplicates, so that free-text organisation names map to one record. | Must | Needed for shared organisation visibility (O12). Stored in the new `organisations` collection. |
| A4 | Pending accounts queue | As an admin, I want a list of pending accounts with filters (date, country, organisation), so that I can work through approvals. | Must | New SIA screen. Shows how long each account has been waiting. |
| A5 | Approval notifications | As a registrant, I want an email when my account is approved or denied. As an admin, I want an email when an account is waiting for review. | Must | Admins on the `registration` email list. Reminder after 48 h pending. |
| A6 | Log in | As an active user, I want to log in with email and password, so that I can use SHOP, SIA or SIA Mobile. | Must | Only `ACTIVE` accounts receive tokens. Other statuses get a clear message. Rate limited, with temporary lockout after 5 failed attempts. |
| A7 | Role-based app access | As the platform, I must allow only `staff` and `admin` into SIA and SIA Mobile; `user` accounts can only use SHOP. | Must | Checked on the server for every request. |
| A8 | Password reset | As a user, I want to reset a forgotten password by email code. | Must | Resetting revokes all of the user's active sessions. |
| A9 | Log out | As a user, I want logging out to end my session immediately. | Must | Token revoked in Redis. |
| A10 | Suspend / reactivate | As an admin, I want to suspend an account and later reactivate it. | Should | Suspending revokes the user's sessions immediately. |
| A11 | Role management | As an admin, I want to change a user's role (`user` / `staff` / `admin`). | Must | Recorded in the audit log. An admin cannot demote themselves if they are the last admin. |
| A12 | Profile | As a user, I want to view and edit my name, phone, organisation, profile image and saved shipping addresses. | Should | Email change requires re-verification. |
| A13 | Audit log | As an admin, I want every approval, role change, suspension and request status change recorded with who, when and why. | Must | Read-only view in SIA, filterable by user, entity and date. Stored in the new `auditlog` collection, which can only be added to, never edited or deleted. |

### 5.2 Catalogue (catalog-svc)

| # | Title | User story | Priority | Notes |
|---|---|---|---|---|
| C1 | Browse catalogue | As a customer, I want to browse sellable products by type (met, radar, equipment, supplies, misc, projects) and department. | Must | Only `sellable` products. **No prices shown.** Cursor-based paging. |
| C2 | Search | As any user, I want to search by name, make, model name or number, serial or keyword and get relevant results quickly. | Must | MongoDB text search replaces the current `$regex` queries. Typo-tolerant search is a Could. |
| C3 | Product detail | As a customer, I want to see a product's images, description, details, make and model, dimensions, weight and availability (in stock / available on request). | Must | Exact stock counts are shown to staff only. |
| C4 | Pro Bono catalogue | As a customer, I want a separate **Pro Bono** items section listing items CIMH provides free. | Must | Keeps today's NCI pages. |
| C4a | Pro Bono item limits | As staff, I want to set an optional maximum quantity per request for each Pro Bono item, so that free stock is shared fairly. | Must | Enforced in the cart and on submission; shown on the product page ("max 2 per request"). |
| C5 | Manage products | As staff, I want to create and edit products (type, department, project, make, model, serials, dimensions, weight, cost, low-stock threshold, keywords, sellable flag, Pro Bono flag). | Must | `cost` is visible to staff only. |
| C6 | Product images | As staff, I want to upload product images and optionally remove the background automatically. | Should | Background removal runs on the media worker in the background. Image types and sizes checked on upload. |
| C7 | Landing samples | As a visitor, I want the SHOP home page to feature a selection of met and radar products. | Could | Replaces `/getsample`. |
| C8 | Departments, types, projects | As an admin, I want to manage the lists of departments, product types and projects. | Should | Currently all stored in the `misc` collection. |

### 5.3 Inventory and warehouse (inventory-svc)

| # | Title | User story | Priority | Notes |
|---|---|---|---|---|
| I1 | Sites, locations, shelves | As staff, I want to register sites, locations within sites, and numbered shelves, each with a printable QR code. | Must | |
| I2 | Unit labels | As staff, I want to generate a batch of unique unit barcodes or QR codes for a product as PDF or CSV. | Must | Each physical unit has its own `storage` record. |
| I3 | Stow | As staff, I want to scan a shelf, then scan units, to record where they are stored. | Must | Web and mobile. Records `stowby`, `stowdate`. |
| I4 | Self-stow / assign | As staff, I want to assign a unit to a person (e.g. equipment issued to an employee). | Should | Replaces `selfstow`. Includes a "who has what" report. |
| I5 | Pick | As staff, I want to scan a unit to remove it from a shelf, with a reason. | Must | Records `pickedby`, `pickeddate`, `pickedreason`. |
| I6 | Relocate | As staff, I want to move units between shelves. | Should | |
| I7 | Lookup | As staff, I want to scan a shelf or product and see its contents or locations, paged. | Must | Web and mobile. |
| I8 | Stock levels | As staff, I want to see stock counts per product and per site, and be alerted when stock falls below the threshold. | Must | Low-stock email sent to staff. |
| I9 | Reservation | As the platform, I must reserve in-stock units for an accepted CIMH stock quote (or an approved Pro Bono request) and release them if it is cancelled, so that units are never oversold. | Must | All units for a request are reserved in one transaction: each `storage` document's `orderid` is set only if currently empty, and if any unit fails, the whole reservation is rolled back. |
| I11 | Stock availability check | As the platform, I must tell order-svc, for each item in a request, whether CIMH stock holds the full requested quantity. | Must | Used to build the CIMH stock quote (O5a). |
| I10 | Movement history | As an admin, I want a history of every stow, pick, relocate and assignment. | Must | Collection `history`. |

### 5.4 Cart and order requests (order-svc)

| # | Title | User story | Priority | Notes |
|---|---|---|---|---|
| O1 | Cart | As a customer, I want to add, change quantity of, and remove items in my cart, and have it saved across devices. | Must | Cart stores product IDs and quantities only, not product copies. |
| O2 | Submit request | As a customer, I want to submit my cart as an order request with a shipping address, notes and a quote currency (**BBD or USD**). | Must | `@cimh.edu.bb` accounts cannot add to cart or submit. A cart with both paid and Pro Bono items is **split into two requests**: one paid, one Pro Bono. |
| O3 | Paid request lifecycle | As the platform, I must move a paid request through `SUBMITTED → QUOTING → QUOTED → AWAITING_AGREEMENT → ACCEPTED → PURCHASING → SHIPPED → DELIVERED`, with `DECLINED → CANCELLED` and cancellation allowed before `PURCHASING`. | Must | Only valid transitions are allowed, each checked atomically. Every change is recorded in `history[]`. |
| O4 | Pro Bono request lifecycle | As the platform, I must move a Pro Bono request through `SUBMITTED → APPROVED → PICKING → SHIPPED → DELIVERED` (or `REJECTED / CANCELLED`), skipping quotes. | Must | Staff approve against stock; the request is fulfilled from CIMH stock only. |
| O5 | Upload quotes | As staff, I want to attach one or more supplier quotes (PDF) to a request, with supplier name, amount (in the request's currency) and expiry date, then send it to the customer. | Must | Request moves to `QUOTED`. A revised quote replaces the current version; earlier versions are kept. |
| O5a | CIMH stock quote | As a customer, when CIMH already holds the **full requested quantity** of an item, I want a second quote from CIMH that supplies that item from stock, so that I can choose it instead of a supplier purchase. | Must | When staff start quoting, the system checks stock for each item (I11). Items fully in stock are listed on a generated **CIMH quote** (PDF, priced from catalogue cost plus the admin fee; catalogue cost is in **BBD**, and for USD requests staff enter the exchange rate, which is saved on the quote and printed on the PDF); staff still collect supplier quotes for the remaining items. The customer chooses, **item by item**, between the CIMH stock option and the supplier option. Items only partly in stock do not get a CIMH option. |
| O6 | Accept / decline quote | As a customer, I want to review the quotes, choose CIMH stock or supplier for each item that has both, then **download the generated payment agreement, sign it and upload it** to accept (committing to pay the total), or decline with a reason. | Must | Choosing options generates an **agreement PDF** stating the total of the chosen quotes (`QUOTED → AWAITING_AGREEMENT`). Uploading the signed agreement makes the request `ACCEPTED`. The customer can change choices before uploading (back to `QUOTED`, new agreement). The quote expiry still applies. Acceptance records timestamp, user, IP, choices and the signed-agreement file. Only the latest quote version can be accepted. Units chosen from CIMH stock are reserved at acceptance (I9); if stock has run out, staff requote that item. |
| O6a | Verify agreement | As staff, I want to check the signed agreement, and either confirm it when recording purchase orders or reject it with a reason so the customer uploads it again. | Must | Rejecting returns the request to `AWAITING_AGREEMENT`. Purchase orders cannot be recorded until the agreement is verified. |
| O7 | Quote expiry | As the platform, I must cancel `QUOTED` requests automatically when the quote expires. | Must | Validity: **30 days**. Customer reminded 3 days before expiry. |
| O8 | Purchasing | As staff, I want to record purchase-order numbers per supplier and mark the request `PURCHASING`. | Must | |
| O9 | Pick for request | As staff, I want to pick units against a request by scanning, on web or mobile. | Must | Replaces `/orders/pick`. **Only lines supplied from CIMH stock (and Pro Bono lines) are picked.** Items bought from suppliers are shipped direct to the customer and are **not** received into stock or tracked as units. |
| O10 | Shipping | As staff, I want to record carrier, tracking number, cost and date, and optionally email the customer. | Must | Request moves to `SHIPPED`. Carriers: **FedEx, DHL, Hand delivered**. Staff or admin enter the tracking number manually once shipped (not required for hand delivery). **No carrier API integration.** The customer sees the carrier, tracking number and a link to the carrier's tracking page. |
| O11 | Delivery | As staff, I want to mark a request `DELIVERED`. | Must | Triggers the final invoice. |
| O12 | Customer request list | As a customer, I want to see my requests **and my organisation's requests**, filtered by status, year and requester, and open any of them to see its timeline, quotes, documents and tracking. | Must | Visibility is limited to the customer's own organisation. Only the requester (or an admin) can accept, decline or cancel a request. |
| O13 | Staff request queue | As staff, I want a queue of requests filtered by status, year, customer, organisation or request ID, with how long each has been waiting. | Must | |
| O14 | Cancel | As a customer, I want to cancel my request before purchasing starts. As staff, I want to cancel with a reason. | Must | Reserved stock is released. |
| O15 | Admin fee | As an admin, I want to set the admin fee added to paid quotes and invoices. | Should | Today stored in the `misc` "fees" document. |

### 5.5 Documents (document-svc)

| # | Title | User story | Priority | Notes |
|---|---|---|---|---|
| D1 | Generated PDFs | As the platform, I must generate quotation, invoice and commercial-invoice PDFs (separate ones for Pro Bono) from request data. | Must | Generated in the background after the relevant Kafka event. |
| D2 | Uploads | As staff, I want to attach files (quotes, supplier invoices, proof of shipment) to a request. | Must | PDF and images only, 20 MB limit, stored under random UUID names on the local volume. |
| D3 | Protected download | As a customer or staff member, I want to download a request's documents, and only if I am allowed to. | Must | Ownership or role checked first, then nginx serves the file via `X-Accel-Redirect`. |
| D4 | Delete upload | As staff, I want to remove a wrongly uploaded file. | Should | Soft delete; recorded in the audit log. |

### 5.6 Notifications (notification-svc)

| # | Title | User story | Priority | Notes |
|---|---|---|---|---|
| N1 | Event emails | As a user, I want an email whenever my account or request changes status. | Must | Driven by Kafka events. Templated HTML with a plain-text fallback. |
| N2 | Staff lists | As an admin, I want to manage email lists for `registration`, `order`, `invoice`, `cancellation` and low-stock alerts. | Must | Replaces `misc` "emails". |
| N3 | Delivery reliability | As the platform, I must retry failed emails and alert operators when an email has permanently failed. | Must | Retry with backoff, then the dead-letter queue (DLQ). |

### 5.7 SIA Mobile (Android)

| # | Title | User story | Priority | Notes |
|---|---|---|---|---|
| M1 | Staff login | As staff, I want to log in on the mobile app and stay signed in securely. | Must | Uses the v2 token flow. Tokens kept in encrypted storage on the device. |
| M2 | Scan | As staff, I want to scan QR codes and barcodes with the camera to identify shelves and units. | Must | Existing `QRSccannerActivity`. |
| M3 | Lookup | As staff, I want to look up a shelf's contents or a product's locations. | Must | Paged, as today. |
| M4 | Stow / pick | As staff, I want to stow and pick units by scanning a shelf, then units. | Must | |
| M5 | Pick requests | As staff, I want to see approved requests and pick their items by scanning. | Must | |
| M6 | Shipping | As staff, I want to record the carrier and tracking number for a request. | Should | Manual entry; no carrier API. |
| M7 | Create product / location | As staff, I want to create products and locations from the device, including photos. | Should | Existing screens. |
| M8 | Offline tolerance | As staff, I want scans made with poor connectivity to be queued and synced when the connection returns. | Could | WorkManager queue already exists. |
| M9 | API migration | As the platform, the mobile app must move from `/sia/api/*` to the v2 service APIs before the Flask app is retired. | Must | |

### 5.8 Platform (non-functional)

| # | Title | Requirement | Priority |
|---|---|---|---|
| P1 | Security | Every endpoint requires authentication, apart from catalogue browsing, registration and login. Authorisation is checked by role and by ownership. No dynamic code execution. User input is validated and safe to use in database queries and regular expressions. Rate limiting is applied. | Must |
| P2 | Transport | TLS 1.2+ only; security headers; cookies are `Secure`, `HttpOnly` and `SameSite`, with CSRF protection. | Must |
| P3 | Scale | Services hold no state, so they can be scaled with `docker compose --scale`. Database connections are pooled. Paging is cursor-based. Indexes cover every query pattern. | Must |
| P4 | Messaging | Kafka with an embedded outbox (pending events stored on the changed document, then published by a relay), consumers that ignore duplicate events, retries and a DLQ, and the entity ID as the message key. | Must |
| P4a | Frontend | SHOP and SIA web are rewritten in **Vue 3 + TypeScript** (Vite, Pinia, file-based routing, Vuetify 4, Zod 4), with API types generated from each service's OpenAPI spec. | Must |
| P5 | Observability | Health checks per service; metrics in Prometheus; structured JSON logs (including errors with stack traces) kept by Docker; email alerts from Alertmanager on errors, latency and Kafka consumer lag. | Must |
| P6 | Backup and recovery | Nightly backup of MongoDB and the file volume to an offsite location; restore tested every quarter. Recovery point objective (RPO) ≤ 24 h; recovery time objective (RTO) ≤ 4 h. The MongoDB replica set (main host plus 2 Raspberry Pis) survives the loss of any one member without losing data or stopping writes. | Must |
| P7 | Accessibility | SHOP and SIA web meet WCAG 2.1 AA; work on phone-sized screens; light and dark themes. | Should |
| P8 | Privacy | Personal data visible only to its owner, staff and admins. Rejected and expired accounts are deleted after 90 days. | Should |

## 6. User interaction and design

Key flows (wireframes TBD):

1. **Registration:** Sign up → enter email code → "Awaiting approval" page → approval email → log in.
2. **Paid request:** Browse/search → add to cart → submit → *Requests* timeline shows `SUBMITTED` → quote email → review supplier quote and, where items are in stock, the CIMH stock quote → choose CIMH or supplier per item → download agreement → sign → upload → **Accepted** (or **Decline**) → tracking → delivered + invoice.
3. **Pro Bono request:** Pro Bono section → add to cart → submit → staff approve → shipped → delivered.
4. **Staff request desk (SIA):** Request queue → open request → upload quotes → (customer signs and uploads the agreement) → verify agreement + record purchase orders → pick CIMH-stock lines (web or mobile) → ship → deliver.
5. **Admin (SIA):** Pending accounts → approve/deny; Users & roles; Email lists; Departments/types/projects; Audit log.
6. **Warehouse (Mobile):** Scan shelf → scan units → stow/pick → confirmation.

Screens in today's apps that are carried over: SHOP *Home, Inventory, InventoryItem, Nci, NciItem, Cart, Orders, OrdersPage, Login, Signup, PasswordReset, Profile, Tour*; SIA *Home, Inventory, Products, Product, Stow, Pick, Orders, Orders (internal), Lookup, Profile, Upload*.

## 7. Questions

| Question | Outcome |
|---|---|
| Which roles exist? | **Resolved:** only `admin`, `staff`, `user`. |
| Which currencies may quotes use? | **Resolved:** BBD or USD. |
| Default quote validity? | **Resolved:** 30 days. |
| Is there a limit on Pro Bono quantities? | **Resolved:** optional maximum per item, set by staff (C4a). |
| Should customers in the same organisation see each other's requests? | **Resolved:** yes (O12). |
| Should `cimh.edu.bb` accounts skip approval? | **Resolved:** yes (A3). |
| How should existing open orders be mapped? | **Resolved:** all to `SUBMITTED`. |
| Which carriers? | **Resolved:** FedEx, DHL, Hand delivered. |
| Can a quote mix BBD and USD? | **Resolved:** no. One currency per request, never both. |
| CIMH stock quote pricing? | **Resolved:** catalogue `cost` plus admin fee. |
| Can `@cimh.edu.bb` users request items? | **Resolved:** no. |
| Catalogue cost currency and conversion? | **Resolved:** cost is stored in BBD. For USD requests, staff enter the exchange rate on each CIMH quote. |
| Replica set layout? | **Resolved:** main host plus 2 Raspberry Pis (see note below). |

**Replica set layout (decided).**

| Member | Machine | Role | Priority |
|---|---|---|---|
| mongo1 | Main host | Primary | 10 |
| mongo2 | Raspberry Pi A | Secondary (full copy of the data) | 1 |
| mongo3 | Raspberry Pi B | Secondary (full copy of the data) | 1 |

- Any one member can fail and the platform keeps accepting writes, because the other two are still a majority.
- If the main host fails, a Pi becomes primary. The platform stays up but slower until the host returns, then the host takes back the primary role automatically (higher priority).
- **Pi hardware requirements:** **Raspberry Pi 5, 8 GB or more** (MongoDB 5.0+ does not run on Pi 4 or older), 64-bit OS, and an **SSD** (NVMe or USB 3) for the database. The current data is roughly 12M documents, so allow at least 2× today's database size. SD cards are not acceptable for the database.
- All three machines on the same network, with fixed IPs or local DNS names. Members talk to each other over TLS with keyfile or certificate authentication.
- Backups (P6) are taken from a Pi secondary, so they don't slow down the primary.

## 8. Not doing

- Online payments, card processing or customer credit accounts.
- Prices on product pages.
- Native iOS app or a customer-facing mobile app.
- Cloud object storage (S3); files stay on a local volume.
- Kubernetes or other orchestration beyond Docker Compose.
- Automated supplier integrations (quotes are collected manually by staff).
- Multi-language support at launch.
