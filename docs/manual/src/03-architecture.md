# 3. Architecture

[← Users, roles and apps](02-users-roles-apps.md) · [Manual home](README.md) · [Next: Data →](04-data.md)

Source: [TAD §2–5](../TAD.md).

## 3.1 System context

![System context](images/01-system-context.svg)

The platform has three clients (SHOP, SIA, SIA Mobile) and one backend. Its only external dependencies are the **CIMH mail server** (all email) and the **backup store at another CIMH site**. FedEx and DHL are **not integrated**; SHOP simply links to their public tracking pages.

## 3.2 Design principles

1. **Each service owns its data.** Only the owning service reads or writes a collection.
2. **Events for facts, HTTP for questions.** Changes of state go to Kafka; direct HTTP calls are used only when an answer is needed immediately.
3. **Services hold no state.** Sessions, limits and locks are in Redis; files are on a shared volume; any replica can serve any request.
4. **Never trust the client.** The server checks login, role and ownership on every request.
5. **Events can't be lost and can be applied twice safely.** The outbox saves the event with the change; consumers detect duplicates.
6. **Keep it simple.** Nothing that Docker Compose on one host plus two Pis can't run.

## 3.3 Containers

![Container view](images/02-containers.svg)

| Container | Responsibility |
|---|---|
| **nginx** | TLS, serves both web apps, routes `/api/*` to services, rate limits, serves public images, protected downloads (`X-Accel-Redirect`) |
| **identity-svc** | Accounts, organisations, login, tokens, approvals, roles, audit log |
| **catalog-svc** | Products, search, Pro Bono items and limits, reference data (`misc`), image records |
| **inventory-svc** | Sites, shelves, storage units, stow, pick, relocate, stock levels, **reservations** |
| **order-svc** | Carts, requests, status flows, supplier and CIMH quotes, acceptance, purchasing, shipping |
| **document-svc** | PDF generation (quotes, invoices, commercial invoices), uploads, permission-checked downloads |
| **notification-svc** | All email, triggered by events |
| **media-worker** ×2 | Background removal on the GPUs, resizing, WebP, barcode decoding |
| **outbox relays** | Publish saved events from each service to Kafka |
| **Kafka ×3 + Apicurio** | Event backbone and event schemas |
| **Redis** | Token revocation, rate limits, idempotency keys, processed-event IDs, locks, cache |
| **MongoDB** | Replica set: primary on the host, secondaries on 2 Raspberry Pi 5 |
| **File volume** | `/srv/sia-data`: PDFs, uploads, product images, QR codes |
| **Prometheus + Alertmanager** | Metrics and email alerts |

### Service profiles

| Service | Owns | Publishes | Consumes | Scheduled jobs |
|---|---|---|---|---|
| identity | `accounts`, `temp`, `organisations`, `auditlog` | `identity.user.events` | `audit.events` | Expire unverified (24 h); remind admins (48 h); purge rejected/expired (90 d) |
| catalog | `product`, `xuser`, `misc` | `catalog.product.events`, `media.jobs` | `media.results`, `inventory.stock.events` | — |
| inventory | `storage`, `history` | `inventory.stock.events` | `order.events` | — |
| order | `orders` (incl. carts) | `order.events` | `document.events`, `inventory.stock.events`, `identity.user.events` | Quote expiry (30 d) + reminder (3 d before) |
| document | none (metadata in `orders.files[]`) | `document.events` | `order.events` | — |
| notification | none | — | identity, order, stock, document events | — |
| media-worker | none | `media.results` | `media.jobs` | — |

**Internal structure of every service:** `api/` (routes) · `domain/` (rules and status flows, no I/O) · `repository/` (the only code that touches MongoDB) · `events/` (outbox, consumers, schemas) · `jobs/` (scheduled work, run only by the leader replica) · `auth/` (shared library).

## 3.4 Edge routing

| Path | Goes to |
|---|---|
| `store.cimh.edu.bb/` | SHOP web app |
| `sia.cimh.edu.bb/` | SIA web app |
| `/api/identity/` · `/api/catalog/` · `/api/inventory/` · `/api/orders/` · `/api/documents/` | The matching service (all replicas, via Docker DNS) |
| `/media/products/` | Public product images (direct from the volume) |
| `/_protected/` | Internal only, reached via `X-Accel-Redirect` |
| `/sia/api/` | Legacy Flask, during the transition only |

Rate limits: 20 requests/s per IP for the API in general; **5 requests/min** for login, register and verification.

## 3.5 Synchronous HTTP calls between services

![Synchronous HTTP calls](images/03-service-communication.svg)

Only five places need an immediate answer from another service (the fifth: notification-svc claims a verification or reset code **once** from identity-svc, because codes must never travel through Kafka). All of them use the internal network with short-lived **service tokens**, a 2 s timeout, a circuit breaker, and return `503` rather than write partial data.

## 3.6 Kafka events

![Kafka topics](images/04-kafka-topics.svg)

**Event envelope** (every message):

```json
{ "eventId": "ULID", "type": "order.accepted", "version": 1, "occurredAt": "2026-11-06T14:03:22Z",
  "correlationId": "trace id", "actorId": "user id", "payload": { } }
```

| Setting | Value |
|---|---|
| Message key | Entity id (`userId`, `productId`, `orderId`), so events for one entity stay in order |
| Partitions | 6–12 per topic (to be confirmed by load tests) |
| Durability | Replication 3 · `min.insync.replicas=2` · `acks=all` · idempotent producers |
| Consumer groups | One per service |
| Retries | `.retry` topic at 1 min → 5 min → 30 min, then `.dlq` (raises an alert) |
| Schemas | Registered in Apicurio, must stay backward compatible; a breaking change means a new `version` |

**Main event types:**

| Topic | Events |
|---|---|
| `identity.user.events` | `user.registered`, `user.verified`, `user.approved`, `user.rejected`, `user.suspended`, `user.reactivated`, `user.role_changed`, `user.profile_updated`, `user.approval_pending`, `user.erasure_requested`, `user.deleted`, `user.password_reset_requested`, `user.email_change_requested` (code events carry only a `codeRef`) |
| `catalog.product.events` | `product.created`, `product.updated`, `product.deleted`, `product.image_added` |
| `inventory.stock.events` | `stock.changed`, `stock.low`, `stock.reserved`, `stock.released`, `stock.reservation_failed`, `unit.stowed`, `unit.picked` |
| `order.events` | `order.submitted`, `order.quoting_started`, `order.quoted`, `order.quote_revised`, `order.accepted`, `order.declined`, `order.probono_approved`, `order.probono_rejected`, `order.purchasing`, `order.shipped`, `order.delivered`, `order.cancelled`, `order.expired` |
| `document.events` | `document.generated`, `document.uploaded`, `document.deleted` |

## 3.7 Outbox: no lost events

![Outbox relay](images/05-outbox-relay.svg)

1. The service writes the state change **and** the event to the same document (`outbox[]`) in one operation.
2. The relay watches for unsent events (change stream, plus a sweep every 30 s), publishes them to Kafka and removes them once acknowledged.
3. An event can occasionally be published twice. Consumers record each `eventId` in Redis (`SET NX`, 7 days) and skip repeats, and apply changes with conditional updates.
