# API Specification: CIMH Stores Platform v2

| | |
|---|---|
| **Document status** | DRAFT (all specs validated) |
| **Document owner** | T. Edwards |
| **Related documents** | [PRD](../PRD.md) · [TRD](../TRD.md) · [TAD](../TAD.md) · [BSD](../BSD.md) · [Manual](../manual/index.html) |
| **Last updated** | 2026-11-06 |

The exact contract for every endpoint (what you send and what you get back) and every Kafka event. The **machine-readable files are the source of truth**; this page explains the conventions and lists every endpoint.

| File | Contents | Validated with |
|---|---|---|
| [common.yaml](common.yaml) | Shared schemas (Problem, Money, Address, Actor, PageMeta…), parameters, responses, security schemes | openapi-spec-validator: OK |
| [identity.openapi.yaml](identity.openapi.yaml) | Auth, profile, approvals, roles, organisations, audit | OK |
| [catalog.openapi.yaml](catalog.openapi.yaml) | Products, search, Pro Bono, images, reference data, settings | OK |
| [inventory.openapi.yaml](inventory.openapi.yaml) | Sites/locations/shelves, units, scans, stock, history, reservations | OK |
| [orders.openapi.yaml](orders.openapi.yaml) | Cart, requests, quotes, acceptance, purchasing, picking, shipping | OK |
| [documents.openapi.yaml](documents.openapi.yaml) | Uploads and permission-checked downloads | OK |
| [events.asyncapi.yaml](events.asyncapi.yaml) | Kafka topics and event payloads (AsyncAPI 3.0) | @asyncapi/cli: valid, 0 errors |

Viewing: open any `.openapi.yaml` in the VS Code OpenAPI extension, Swagger Editor or Redocly. At runtime, each service also serves its generated spec at `/api/<service>/v1/openapi.json` and docs at `/docs`. CI checks the running spec against these files to catch drift.

---

## 1. Conventions

| Topic | Rule |
|---|---|
| Base paths | `/api/identity/v1`, `/api/catalog/v1`, `/api/inventory/v1`, `/api/orders/v1`, `/api/documents/v1` (nginx routes to the service) |
| Versioning | Major version in the path (`v1`). Adding fields or endpoints is non-breaking. Removing or renaming anything needs `v2`, with both versions live for ≥ 90 days |
| Format | JSON (`application/json`), UTF-8. Errors use `application/problem+json`. Uploads use `multipart/form-data` |
| Field names | camelCase in the API. The database keeps legacy names where the BSD says so; services map between them |
| Ids | Strings: `USR…`, `ORG…`, `ORD…`, `CRT…`, `QTE…`, `FIL…`. Products, units and shelves keep their legacy barcodes |
| Dates | ISO-8601 UTC (`2026-11-06T14:03:22Z`); date-only fields are `YYYY-MM-DD`. The UI shows America/Barbados time |
| Money | **String** with 2 decimals (`"1250.00"`), never a float. Catalogue cost is BBD; quotes carry `currency` (`BBD` or `USD`, never both) |
| Nullability | Optional fields may be absent **or** `null`; clients must handle both |
| Unknown fields | Request bodies reject unknown fields (`422`). Responses may add fields at any time, so clients must ignore unknown ones |
| Paging | Cursor-based: `?limit=` (≤ 100, default 25) & `?cursor=`. Responses carry `{ items, nextCursor }`, and `nextCursor: null` means the end. No offset paging |
| Sorting / filtering | Query parameters listed per endpoint only. No generic query language |
| Concurrency | Mutable resources return `version` and an `ETag`. State changes need `If-Match: "<version>"`; a stale version returns **409** |
| Idempotency | `Idempotency-Key` header (ULID/UUID) on `POST /requests` and **required** on every scan (`/stow`, `/pick`, `/relocate`, `/assign`, `/unassign`, `/requests/{id}/picks`). A repeat within 24 h returns the original response |
| Allowed actions | `Request.allowedActions` lists what the caller may do right now. UIs show buttons from it instead of re-implementing the rules |
| Tracing | Every response has `X-Trace-Id`; send `traceparent` if you have one |
| Health | Every service: `GET /health/live`, `GET /health/ready` (no auth) |

## 2. Authentication

| Client | How |
|---|---|
| SHOP / SIA web | `POST /auth/login` sets **HttpOnly, Secure, SameSite=Lax** cookies (`access_token` 15 min, `refresh_token` 7 days, path-scoped) plus a readable `csrf_token` cookie. Every POST/PUT/PATCH/DELETE must echo it in **`X-CSRF-Token`** |
| SIA Mobile | `POST /auth/login` with `client: "mobile"` returns `accessToken` + `refreshToken` in the body (stored in Android Keystore). Send `Authorization: Bearer <accessToken>` |
| Refresh | `POST /auth/refresh` issues a new access token **and a new refresh token**. Reusing an old refresh token revokes the whole session (`401 TOKEN_REUSE`) |
| Services | `POST /internal/service-token` (internal network only) → 5-minute bearer token. Every `/internal/*` endpoint requires one and is **not routed by nginx** |
| Token checks | Every service verifies the EdDSA signature using identity's JWKS (`/.well-known/jwks.json`, cached 10 min), then checks the Redis revocation list |
| Account status | Tokens are issued **only to ACTIVE accounts**. Login for other statuses returns `403` with a specific `code` |

**Rate limits:**
- nginx: 20 requests/s per IP for the API in general; **5/min per IP** on `/auth/register`, `/auth/login`, `/auth/verify*` and `/auth/password/*`.
- Per-account limits are enforced in Redis.
- Exceeding a limit returns `429` with `Retry-After`.

## 3. Roles and access

| Area | Anonymous | `user` (member org) | `user` (`@cimh.edu.bb`) | `staff` | `admin` |
|---|---|---|---|---|---|
| Browse/search catalogue, reference | ✓ (public fields) | ✓ | ✓ | ✓ (+ cost, serials) | ✓ |
| Cart, submit request | — | ✓ | **403 CIMH_CANNOT_REQUEST** | — | — |
| View requests | — | Own + own organisation | — | All | All |
| Accept / decline / cancel | — | Requester only | — | Cancel | All |
| Staff request actions | — | — | — | ✓ | ✓ |
| Products create/edit, images | — | — | — | ✓ | ✓ |
| Inventory API (all) | — | — | — | ✓ | ✓ |
| Upload files | — | `upload` kind on own requests | — | ✓ | ✓ |
| Accounts list/view | — | Self (`/me`) | Self | Read | ✓ |
| Approve/deny, roles, suspend, organisations, settings, email lists, audit | — | — | — | — | ✓ |

Requests for data the caller isn't allowed to see return **404**, not 403, so a caller can't confirm the data exists.

## 4. Errors

Every error is an RFC 9457 **Problem**:

```json
{
  "type": "https://errors.cimh.edu.bb/order/illegal-transition",
  "title": "Illegal status transition",
  "status": 409,
  "code": "ORDER_ILLEGAL_TRANSITION",
  "detail": "Request ORD… is DELIVERED; cannot cancel.",
  "traceId": "a1b2c3…",
  "errors": []
}
```

| Status | Meaning |
|---|---|
| 400 | Malformed JSON or headers |
| 401 | Not logged in, token expired or revoked |
| 403 | Logged in but not allowed (role, account status, CIMH restriction) |
| 404 | Not found **or not visible to the caller** |
| 409 | Version conflict, illegal transition, duplicate |
| 413 / 415 | File too large / unsupported type |
| 422 | Validation failed (`errors[]` lists fields) |
| 429 | Rate limited |
| 503 | A dependency is down; nothing was written; safe to retry |

**Implicit responses.** To keep the specs readable, these are not repeated on every operation, but any
operation may return them (all as `application/problem+json`): **401** and **403** if the operation is
secured; **422** if it takes a body, query or path parameters; **428** (`PRECONDITION_REQUIRED`) if it takes
`If-Match`; **400**, **429** and **503** always. Every
other status must be listed on the operation. The Schemathesis contract tests apply exactly this rule.

**Strict bodies.** Request bodies are validated strictly: a number sent as a string, or `true` for an integer, is a 422 (never coerced).

**Stable `code` values:**

| Area | Codes |
|---|---|
| Auth | `ACCOUNT_PENDING_VERIFICATION`, `ACCOUNT_PENDING_APPROVAL`, `ACCOUNT_REJECTED`, `ACCOUNT_SUSPENDED`, `ACCOUNT_LOCKED`, `MFA_REQUIRED`, `TOKEN_REUSE`, `CODE_INVALID`, `CODE_EXPIRED`, `PASSWORD_BREACHED`, `LAST_ADMIN`, `INVALID_CREDENTIALS`, `MFA_INVALID`, `MFA_ALREADY_ENABLED`, `TOKEN_EXPIRED`, `TOKEN_REVOKED`, `TOKEN_INVALID`, `CSRF_FAILED` |
| Accounts / organisations | `ACCOUNT_ILLEGAL_TRANSITION`, `DUPLICATE`, `ORG_MERGE_INVALID` |
| Orders | `CIMH_CANNOT_REQUEST`, `PROBONO_LIMIT_EXCEEDED`, `PRODUCT_UNAVAILABLE`, `CURRENCY_REQUIRED`, `ORDER_ILLEGAL_TRANSITION`, `QUOTE_OUTDATED`, `QUOTE_EXPIRED`, `QUOTE_INCOMPLETE`, `AGREEMENT_REQUIRED`, `AGREEMENT_NOT_VERIFIED`, `LINE_NOT_PICKABLE`, `LINE_FULLY_PICKED`, `UNIT_WRONG_PRODUCT`, `PICKING_INCOMPLETE`, `EXCHANGE_RATE_REQUIRED`, `CHOICE_REQUIRED`, `TRACKING_REQUIRED` |
| Inventory | `UNIT_NOT_FOUND`, `SHELF_NOT_FOUND`, `UNIT_NOT_STOWED`, `UNIT_ALREADY_STOWED` (on another shelf: relocate instead), `UNIT_ALREADY_PICKED`, `UNIT_RESERVED`, `UNIT_NOT_RESERVED_FOR_ORDER`, `UNIT_ASSIGNED` (issued to a person: unassign first), `UNIT_NOT_ASSIGNED`, `RESERVATION_FAILED` |
| General | `VERSION_CONFLICT`, `PRECONDITION_REQUIRED` (428: `If-Match` missing), `VALIDATION_FAILED`, `RATE_LIMITED`, `DEPENDENCY_UNAVAILABLE`, `IDEMPOTENCY_KEY_REUSED` (422: same key, different request), `IDEMPOTENCY_IN_PROGRESS` (409: the first request with this key is still running; retry), `SEARCH_BUSY` (503 + `Retry-After`: too many searches at once, or a broad query hit its time limit) |

## 5. Endpoint catalogue

### identity-svc: `/api/identity/v1`
| Method | Path | Role | Purpose |
|---|---|---|---|
| POST | `/auth/register` | public | Register (always 202) |
| POST | `/auth/verify` · `/auth/verify/resend` | public | Email code |
| POST | `/auth/login` · `/auth/refresh` · `/auth/logout` | public / any | Session |
| POST | `/auth/password/forgot` · `/auth/password/reset` | public | Password reset |
| POST | `/auth/mfa/setup` · `/auth/mfa/confirm` | admin | TOTP |
| GET | `/.well-known/jwks.json` | public | Token verification keys |
| GET / PATCH | `/me` | any | Own profile (PATCH needs If-Match) |
| POST | `/me/email` · `/me/password` | any | Change email or password |
| GET | `/me/export` | any | Download own personal data (JSON attachment) |
| POST | `/me/erasure-request` | any | Ask to be deleted (password confirms; an admin erases) |
| GET | `/admin/accounts` · `/admin/accounts/{id}` | staff, admin | Accounts and the approval queue (`?status=PENDING_APPROVAL`) |
| POST | `/admin/accounts/{id}/approve` · `/deny` | admin | Approval decision (approve needs `organisationId`) |
| POST | `/admin/accounts/bulk-decision` | admin | Up to 100 decisions (207) |
| POST | `/admin/accounts/{id}/suspend` · `/reactivate` | admin | Suspension |
| POST | `/admin/accounts/{id}/mfa/reset` | admin | Reset another admin's lost authenticator (revokes sessions; audited) |
| PUT | `/admin/accounts/{id}/role` | admin | Role change |
| GET | `/admin/accounts/{id}/export` | admin | Export a person's data |
| POST | `/admin/accounts/{id}/erase` | admin | Erase a person's data (reason, If-Match; 204) |
| GET / POST | `/organisations` | staff / admin | List, create |
| GET / PATCH | `/organisations/{id}` | staff / admin | View, edit |
| POST | `/organisations/{id}/merge` | admin | Merge duplicates |
| GET | `/audit` | admin | Audit log |
| POST | `/internal/service-token` · GET `/internal/accounts/{id}` | service | Internal |
| GET | `/internal/codes/{codeRef}` | service (notification only) | Claim a verification/reset/email-change code once, to email it |

### catalog-svc: `/api/catalog/v1`
| Method | Path | Role | Purpose |
|---|---|---|---|
| GET | `/products` | public | Browse (filters: type, department, project, `probono`, inStock; staff also `sellable`, `includeInactive`) |
| GET | `/products/search?q=` | public | Full-text search (ranked; a word matching more than 300 products is ranked over the first 300 matches and pages stop there: refine the words) |
| GET | `/products/{id}` | public | Detail (staff view adds cost, serials, stockCount) |
| POST / PATCH / DELETE | `/products` · `/products/{id}` | staff | Create (`probono` required), edit, deactivate |
| POST | `/products/{id}/images` | staff | Upload (async processing; background removal optional) |
| PATCH / DELETE | `/products/{id}/images/{fileId}` | staff | Make primary, remove |
| GET | `/reference` | public | Departments, types, active projects (staff: `includeInactive=true` lists all) |
| PUT | `/reference/departments` · POST `/reference/projects` · PATCH `/reference/projects/{code}` | admin | Reference data |
| GET / PUT | `/settings/fees` · `/settings/email-lists` · `/settings/general` | staff read / admin write | Admin fee, notification lists, workflow settings |
| POST | `/internal/products/summaries` · GET/PUT `/internal/places` | service | Internal |

### inventory-svc: `/api/inventory/v1` (staff and admin only)
| Method | Path | Purpose |
|---|---|---|
| GET / POST | `/sites` | Sites |
| GET / POST | `/sites/{site}/locations` | Locations |
| POST | `/locations/{location}/shelves` | Add shelves (QR) |
| GET | `/shelves/{barcode}` · `/shelves/{barcode}/units` | Validate shelf; lookup contents |
| GET | `/units/{barcode}` | Unit detail |
| POST | `/labels` | Create N units + label PDF/CSV |
| POST | `/stow` · `/pick` · `/relocate` · `/assign` · `/unassign` | Scans (**Idempotency-Key required**) |
| GET | `/products/{id}/stock` · `/stock/low` · `/assignments` · `/history` | Stock, low stock, who has what, movement log |
| POST | `/internal/availability` · `/internal/reservations` · DELETE `/internal/reservations/{orderId}` | Internal (order-svc) |

### order-svc: `/api/orders/v1`
| Method | Path | Role | Transition |
|---|---|---|---|
| GET / DELETE | `/cart` | user | — |
| PUT / DELETE | `/cart/lines/{productId}` | user | — |
| POST | `/requests` | user | → `SUBMITTED` (1 or 2 requests) |
| GET | `/requests` · `/requests/{id}` | user (own/org) · staff | — |
| POST | `/requests/{id}/agreement` | requester, admin | `QUOTED → AWAITING_AGREEMENT` (choices; agreement PDF generated) |
| POST | `/requests/{id}/accept` | requester, admin | `AWAITING_AGREEMENT → ACCEPTED` (signed agreement file) |
| POST | `/requests/{id}/reject-agreement` | staff | `ACCEPTED → AWAITING_AGREEMENT` (signature not acceptable) |
| POST | `/requests/{id}/decline` | requester, admin | `QUOTED → DECLINED → CANCELLED` |
| POST | `/requests/{id}/cancel` | requester, staff, admin | → `CANCELLED` (up to ACCEPTED/APPROVED) |
| POST | `/requests/{id}/start-quoting` | staff | `SUBMITTED → QUOTING` (+ stock check) |
| PUT | `/requests/{id}/quote-draft` | staff | Draft supplier + CIMH options, exchange rate |
| POST | `/requests/{id}/send-quote` | staff | `QUOTING → QUOTED` (or revise) |
| POST | `/requests/{id}/purchase-orders` | staff | `ACCEPTED → PURCHASING` (needs `agreementVerified: true`) |
| POST | `/requests/{id}/approve` · `/reject` | staff | Pro Bono: `SUBMITTED → APPROVED / REJECTED` |
| POST | `/requests/{id}/picks` | staff | Pick a unit for a **CIMH-stock or Pro Bono line** (Pro Bono `APPROVED → PICKING`); supplier lines are never picked |
| POST | `/requests/{id}/ship` | staff | `→ SHIPPED` (carrier; tracking unless HAND) |
| POST | `/requests/{id}/deliver` | staff | `SHIPPED → DELIVERED` (+ invoice) |
| GET / POST | `/internal/requests/{id}/access` · `/internal/requests/{id}/files` · `/internal/requests/{id}` | service | Internal (document-svc: access + state, attach, staff view for PDFs) |

Catalog internal (service token): `GET /internal/email-lists` (notification-svc: staff lists with emails).

### document-svc: `/api/documents/v1`
| Method | Path | Role | Purpose |
|---|---|---|---|
| POST | `/files` | staff; user (`signed_agreement` on own request) | Upload (≤ 20 MB; PDF/JPEG/PNG/WebP) |
| GET | `/files/{id}` | allowed viewers | Download (streamed by nginx via X-Accel-Redirect) |
| DELETE | `/files/{id}` | staff | Soft delete with a reason (generated documents cannot be deleted) |
| POST | `/internal/labels` | service (inventory) | Render a unit-label PDF (QR + text) for barcodes just allocated |

Upload errors: 413 `FILE_TOO_LARGE`, 415 `UNSUPPORTED_FILE_TYPE` (type read from the bytes, not the name), 422 `FILE_INFECTED` (ClamAV found malware; the file is quarantined, never stored), 409 `INVALID_STATE` (customer upload outside AWAITING_AGREEMENT), 503 when the scanner is down (fail closed).

## 6. Events (Kafka)

See [events.asyncapi.yaml](events.asyncapi.yaml). Topics: `identity.user.events`, `catalog.product.events`, `inventory.stock.events`, `order.events`, `document.events`, `media.jobs`, `media.results`, `audit.events` (+ `.retry` and `.dlq` for each). Every message uses the envelope `{ eventId, type, version, occurredAt, correlationId, actorId, payload }`, keyed by entity id.

## 7. Mapping from the legacy Flask API

| Legacy `/sia/api/...` | v2 |
|---|---|
| `login`, `token/auth`, `token/refresh`, `logout` | identity `/auth/*` |
| `register`, `verification/*` | identity `/auth/register`, `/auth/verify`, `/auth/password/*` |
| `user/<id>`, `account`, `status`, `auth` | identity `/me` |
| `staff/all`, `client/all` | identity `/admin/accounts?role=` |
| `products`, `products/ext`, `pagecounts`, `products/search*`, `singleproduct*` | catalog `/products`, `/products/search`, `/products/{id}` (no page counts: cursor paging) |
| `inventory/product`, `inventory/productimage`, `inventory/del/image`, `upload/rmbkgrnd` | catalog `/products`, `/products/{id}/images` |
| `misc/depts`, `misc/projects`, `misc/emaillist*` | catalog `/reference`, `/settings/email-lists` |
| `inventory/createsite`, `newlocation`, `newshelf`, `site/locations/*`, `get/shelves/all` | inventory `/sites`, `/sites/{s}/locations`, `/locations/{l}/shelves` |
| `inventory/stow`, `pick`, `selfstow` | inventory `/stow`, `/pick`, `/assign` |
| `inventory/shelfstocks*`, `lookup/page/*`, `singleproductwithloc`, `products/locations` | inventory `/shelves/{b}/units`, `/units/{b}`, `/products/{id}/stock` |
| `staff/assigned`, `user/items` | inventory `/assignments` |
| `product/stockcnt` | inventory `/stock/low` |
| `qrcode/*`, `inventory/barcode/*` | inventory `/labels`; shelf QR as public image |
| `decode` | media-worker (barcode decode during uploads); scanning is done on the device |
| `cart/update`, `cart/get` | orders `/cart` |
| `order/place` | orders `POST /requests` |
| `orders/*`, `order/all`, `orders/pagecount/*` | orders `GET /requests` |
| `orders/pick` | orders `/requests/{id}/picks` |
| `orders/shipping` | orders `/requests/{id}/ship` |
| `orders/invoice`, `orders/invoice/ci`, `order/invcreate`, `order/getquote`, `order/invoice/*`, `invoice/*` | Generated by document-svc from events; download `/files/{id}` |
| `inventory/order/fileupload`, `filedelete`, `inventory/orderfiles/*` | documents `/files` |
| `images/*` | `/media/products/...` (public, nginx) |
| `send/<code>`, `home`, `csrf-token`, `service`, `some/metradar`, `getsample*` | Removed (samples → `GET /products?type=MET&limit=…`) |

## 8. Open questions

| # | Question | Outcome |
|---|---|---|
| 1 | Can customers upload files to their own requests? | **Resolved:** yes: the **signed payment agreement** (kind `signed_agreement`). Uploading it is how a quote is accepted. |
| 2 | Are supplier-bought items received into stock? | **Resolved:** no: they ship **direct** to the customer and are not tracked as units; only CIMH-stock and Pro Bono lines are picked. |
