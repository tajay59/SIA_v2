# 10. API

[← Documentation map and glossary](09-documentation-glossary.md) · [Manual home](README.md) · [Next: App flows →](11-app-flows.md)

Source: [API Specification](../api/README.md) (OpenAPI 3.1 per service + AsyncAPI 3.0 for events; every file validated). The YAML files are the source of truth.

## 10.1 Services and base paths

| Service | Base path | Spec | Who calls it |
|---|---|---|---|
| identity | `/api/identity/v1` | [identity.openapi.yaml](../api/identity.openapi.yaml) | All clients |
| catalog | `/api/catalog/v1` | [catalog.openapi.yaml](../api/catalog.openapi.yaml) | All clients (public browsing) |
| inventory | `/api/inventory/v1` | [inventory.openapi.yaml](../api/inventory.openapi.yaml) | SIA, Mobile (staff only) |
| orders | `/api/orders/v1` | [orders.openapi.yaml](../api/orders.openapi.yaml) | SHOP, SIA, Mobile |
| documents | `/api/documents/v1` | [documents.openapi.yaml](../api/documents.openapi.yaml) | All clients |
| events | Kafka | [events.asyncapi.yaml](../api/events.asyncapi.yaml) | Services only |

Shared schemas (Problem, Money, Address, paging) live in [common.yaml](../api/common.yaml).

## 10.2 Conventions at a glance

| Topic | Rule |
|---|---|
| Format | JSON; errors as RFC 9457 `application/problem+json` with a stable `code` and `traceId` |
| Versioning | `v1` in the path; additions are non-breaking; breaking changes mean `v2`, with both live ≥ 90 days |
| Money | String with 2 decimals (`"1250.00"`), never a float; `currency` BBD or USD |
| Dates | ISO-8601 UTC |
| Paging | `?limit` (≤ 100) + `?cursor`, giving `{ items, nextCursor }`; no offsets or page counts |
| Concurrency | `version` + `ETag`; state changes send `If-Match`; stale gives **409** |
| Idempotency | `Idempotency-Key` on request submission and **required on every scan** (safe for the mobile offline queue) |
| UI buttons | `Request.allowedActions` says what the caller may do now |
| Hidden data | Returns **404**, not 403, for resources the caller can't see |
| Unknown fields | Rejected in requests (`422`), ignored in responses |

## 10.3 Login from each client

![Login, refresh and revocation](images/18-auth-tokens.svg)

| Client | Mechanism |
|---|---|
| SHOP / SIA | HttpOnly cookies + `X-CSRF-Token` header (double-submit) |
| SIA Mobile | `client: "mobile"` login → Bearer tokens in Keystore; refresh issues a new refresh token each time |
| Services | `/internal/service-token` (5 min), internal network only; `/internal/*` is never routed by nginx. Service tokens are refused on user endpoints. `GET /internal/codes/{codeRef}` lets notification-svc (only) claim a code once |

Rate limits are 20 requests/s per IP for the API in general and 5/min on auth endpoints. Exceeding them returns `429` with `Retry-After`.

**Implicit responses.** To keep the specs readable, these are not repeated on every operation, but any
operation may return them (all as `application/problem+json`): **401** and **403** if the operation is
secured; **422** if it takes a body, query or path parameters; **428** (`PRECONDITION_REQUIRED`) if it takes `If-Match`; **400**, **429** and **503** always. Every
other status must be listed on the operation. The Schemathesis contract tests apply exactly this rule.

**Strict bodies.** Request bodies are validated strictly: a number sent as a string, or `true` for an integer, is a 422 (never coerced).

## 10.4 The request (order) API: state machine as endpoints

| Endpoint (`/api/orders/v1/requests/{id}/…`) | Who | Paid flow | Pro Bono flow |
|---|---|---|---|
| `POST /requests` (submit cart) | customer | → `SUBMITTED` | → `SUBMITTED` (mixed cart → 2 requests) |
| `start-quoting` | staff | `SUBMITTED → QUOTING` (stock check) | — |
| `PUT quote-draft` | staff | supplier prices + CIMH option (+ exchange rate if USD) | — |
| `send-quote` | staff | `QUOTING → QUOTED` (30 days; re-send = new version) | — |
| `agreement` | requester/admin | `QUOTED → AWAITING_AGREEMENT` (choice per line; agreement PDF generated) | — |
| `accept` | requester/admin | `AWAITING_AGREEMENT → ACCEPTED` (signed agreement file id) | — |
| `reject-agreement` | staff | `ACCEPTED → AWAITING_AGREEMENT` (bad signature, reason) | — |
| `decline` | requester/admin | `QUOTED → DECLINED → CANCELLED` | — |
| `purchase-orders` | staff | `ACCEPTED → PURCHASING` (agreement verified) | — |
| `approve` / `reject` | staff | — | `SUBMITTED → APPROVED / REJECTED` |
| `picks` | staff | pick **CIMH-stock lines only** (supplier items ship direct) | `APPROVED → PICKING` |
| `ship` | staff | `PURCHASING → SHIPPED` | `PICKING → SHIPPED` |
| `deliver` | staff | `SHIPPED → DELIVERED` | `SHIPPED → DELIVERED` |
| `cancel` | requester/staff/admin | up to `AWAITING_AGREEMENT` (customer); `ACCEPTED` staff/admin only | `SUBMITTED` (customer); `APPROVED` staff/admin only |

Every illegal action returns **409 `ORDER_ILLEGAL_TRANSITION`**; a stale `If-Match` returns 409 `VERSION_CONFLICT`. The admin fee is charged once per request and included in the agreement total. Shipping needs every CIMH-stock and Pro Bono unit picked first (409 `PICKING_INCOMPLETE`).

Status diagrams: [Chapter 5](05-workflows.md#53-paid-request-quote-to-delivery).

## 10.5 Endpoint summary

| Service | Main endpoints |
|---|---|
| identity | `/auth/register`, `/auth/verify`, `/auth/login`, `/auth/refresh`, `/auth/logout`, `/auth/password/*`, `/auth/mfa/*`, `/.well-known/jwks.json`, `/me`, `/admin/accounts` (+ `approve`, `deny`, `bulk-decision`, `suspend`, `reactivate`, `role`), `/organisations` (+ `merge`), `/audit` |
| catalog | `/products` (browse, create), `/products/search`, `/products/{id}`, `/products/{id}/images`, `/reference`, `/settings/fees`, `/settings/email-lists`, `/settings/general` |
| inventory | `/sites`, `/sites/{s}/locations`, `/locations/{l}/shelves`, `/shelves/{b}` (+ `/units`), `/units/{b}`, `/labels`, `/stow`, `/pick`, `/relocate`, `/assign`, `/unassign`, `/products/{id}/stock`, `/stock/low`, `/assignments`, `/history` |
| orders | `/cart`, `/cart/lines/{productId}`, `/requests`, `/requests/{id}` + the actions in §10.4 |
| documents | `POST /files`, `GET /files/{id}` (X-Accel-Redirect), `DELETE /files/{id}` |

The full catalogue with roles, and the **legacy → v2 endpoint mapping**, is in the [API Specification](../api/README.md#5-endpoint-catalogue).

## 10.6 Error codes clients should handle

| Code | When | UI behaviour |
|---|---|---|
| `ACCOUNT_PENDING_APPROVAL` | Login before approval | Show the "awaiting approval" page |
| `CIMH_CANNOT_REQUEST` | `@cimh.edu.bb` user uses the cart | Hide cart actions |
| `PROBONO_LIMIT_EXCEEDED` | Pro Bono quantity above the item maximum | Show the maximum |
| `QUOTE_OUTDATED` / `QUOTE_EXPIRED` | Accepting an old or expired quote | Reload the request |
| `VERSION_CONFLICT` (409) | Someone else changed it first | Reload and retry |
| `UNIT_RESERVED` / `UNIT_NOT_RESERVED_FOR_ORDER` | Wrong unit scanned | Warn the scanner |
| `TOKEN_REUSE` | Stolen or duplicated refresh token | Force a new login |
| `MFA_REQUIRED` | Admin login without a code, or admin token before MFA setup | Ask for the authenticator code / start MFA setup |
| `ACCOUNT_LOCKED` (403, `Retry-After`) | 5 failed logins | Show when to try again |
| `PRECONDITION_REQUIRED` (428) | Change sent without `If-Match` | Client bug: always send the version |
| `ACCOUNT_ILLEGAL_TRANSITION` (409) | Approving/suspending an account in the wrong status | Reload the account |

## 10.7 Decisions

- Customers upload the **signed payment agreement** (`signed_agreement`) to their own requests; that upload is what accepts the quote.
- Supplier-bought items are **shipped direct**: never stowed and never tracked as units.
