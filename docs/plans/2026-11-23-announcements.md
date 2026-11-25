# Change plan: Announcements (live banner on every page)

Date: 2026-11-23 · Status: **D1–D10 accepted as recommended (owner, 2026-11-23); built the same day on branch `feat/announcements` (one branch, not two PRs)** · Owner request 2026-11-23

**As built (differences from the plan below):** product links added by the owner (`link.productId`; SHOP `/catalogue/<id>`, SIA `/products/<id>`; must be active, and on SHOP when SHOP shows it: 422 `PRODUCT_NOT_FOUND` / `PRODUCT_NOT_ON_SHOP`); audit entries ride on the `misc` document `announcements` (a message can vanish before the relay reads an outbox on it); A-22 built with /impeccable (owner chose "List beside the record"; finish review fix → ship); dev catalog-push has no `PUSH_ORIGINS` (Origin must match the proxied Host, any preview port); production keeps the same-host rule; `deploy/mongo/roles.js` gives `svc_catalog` the new collection; Redis ACL `&cat:ann:*`; CI e2e starts catalog-push. **Owner, for staging:** run `deploy/staging-lite/deploy.sh --edge` once (installs the new stream location on the shared printit-nginx edge; it runs `nginx -t` and restores the old site on failure; the certificate exists, so certbot is not run). Without it SHOP/SIA on staging fall back to polling every 2 min.

Working plan, not part of the manual. When it is built, the affected docs and manual chapters change (§9) and this file records progress.

## 1. What the owner wants

1. An administrator **creates, edits and deletes messages** in SIA's admin section: product information and changes, price changes, general information.
2. A published message appears **at once, without a reload**, as an **information or alert banner at the very top of the site, on every page** (pushed over a WebSocket).
3. The message is **stored in the database**, so a reload or a new visitor still sees it.
4. The administrator sets a **TTL**: how long the message stays. When it runs out, the message disappears from screens and is removed from the database.

## 2. What exists today

| Today | Needed |
|---|---|
| No real-time channel anywhere (all screens poll or reload; no WebSocket/SSE code in services, nginx or the web apps) | One push channel from the server to every open SHOP/SIA tab |
| Site-wide admin content lives in catalog-svc (`misc`: fees, email lists, workflow, reference) | A collection for announcements with automatic expiry |
| nginx proxies plain HTTP (`deploy/nginx/templates/sites.conf.template`, `snippets/proxy.conf`); CSP has no `connect-src` (falls back to `default-src 'self'`) | WebSocket upgrade on one path, connection limits, explicit `connect-src` |
| Redis use: revocation, rate limits, idempotency, locks, cache | Plus one pub/sub channel (catalog only) |
| SHOP and SIA shells have no space above the app bar | A banner area above the app bar, in the Vuetify layout, on every page incl. sign-in pages |

**Rule to note:** "Customers never see prices on product pages". A banner is free text an administrator writes, so a price-change message is their call; the system does not block it (D8 keeps it plain text, no product price fields pulled in).

## 3. Decisions for the owner (recommendation first)

| # | Question | Recommended | Alternative |
|---|---|---|---|
| D1 | Transport | **WebSocket** (as asked): one socket per tab, server → client only, snapshot on connect + changes after | Server-Sent Events: one-way by design, plain HTTP, browser reconnects by itself, no upgrade config in nginx. Simpler for a one-way banner; it would replace §4.4's socket with `text/event-stream` and change nothing else |
| D2 | Where banners show | **Audience per message: SHOP, SIA or both.** SHOP shows them to everyone incl. signed-out visitors and sign-in pages; SIA only to signed-in staff | SHOP only |
| D3 | Who manages them | **Admins only** (audited like other admin changes) | Staff too |
| D4 | TTL | **Presets 1 hour · 1 day · 1 week · 30 days, or a custom end date; at most 90 days.** Stored as an end time (`expiresAt`); editing can shorten or extend it; "End now" deletes | Free number of hours/days, no cap |
| D5 | Can viewers close a banner? | **Information: yes** (remembered in that browser until the message is edited). **Alert: no** | Both closable / neither closable |
| D6 | Several at once | **Up to 3 shown, alerts first, then newest**; more fold behind "n more" | One at a time (newest wins) |
| D7 | Scheduled start | **Optional "Show from" time** (default now); scheduled ones wait in the admin list | Publish immediately only |
| D8 | Content | **Plain text, ≤ 280 characters, plus one optional link** (label + `https://` URL or a site path like `/catalogue/MET…`). No HTML or Markdown | Rich text (needs sanitising and a bigger XSS surface) |
| D9 | Where the socket runs | **A separate `catalog-push` container from the catalog-svc image** (own command, only the stream + list routes, `mem_limit` 256 MB): thousands of idle sockets never compete with catalogue reads, and it restarts on its own | Inside catalog-svc's existing workers |
| D10 | Also email or mobile? | **No.** Email has notification-svc; SIA Mobile is out of scope (could poll the list endpoint later) | Mirror to email lists / SIA Mobile |

## 4. Target design (assumes the recommended answers)

### 4.1 Data: new collection `announcements` ✚ (catalog-svc, BSD §5.12)

| Field | Type | Notes |
|---|---|---|
| `id` | string | `ANN<32 hex>` |
| `message` | string | 1–280 chars, plain text, trimmed |
| `tone` | enum | `INFO` \| `ALERT` |
| `audience` | enum | `SHOP` \| `SIA` \| `BOTH` |
| `link` | object? | `{ label ≤ 40, url }`; `url` = `https://…` or a path starting `/` (no `//`, no `javascript:`) |
| `dismissible` | bool | forced `false` for `ALERT` (D5) |
| `startsAt` | date | default now (D7) |
| `expiresAt` | date | from the TTL; `startsAt < expiresAt ≤ now + 90 d` (D4) |
| `createdBy`, `updatedBy` | Actor | as elsewhere |
| `createdAt`, `updatedAt`, `version` | | `version` for If-Match; also the dismiss key |

Indexes: **TTL index `{ expiresAt: 1 }, expireAfterSeconds: 0`** (MongoDB removes the document after expiry; the monitor runs about every 60 s, so every read also filters `expiresAt > now`), and `{ audience: 1, startsAt: 1 }`. `$jsonSchema` validator in `catalog_svc/schemas.py` (BSD §7). Retention: gone at expiry; the audit log keeps who published what (created / updated / deleted, via `audit.events`, message text included). No personal data in the document beyond the admin Actor.

### 4.2 API (`docs/api/catalog.openapi.yaml`, regenerate `packages/web-api` client)

| Method + path | Who | Does |
|---|---|---|
| `GET /announcements?app=shop\|sia` | anyone (`sia` = staff only, else 403) | Live messages now (`startsAt ≤ now < expiresAt`) for that app; `Cache-Control: no-store`; also the polling fallback |
| `GET /admin/announcements` | admin | Live + scheduled, newest first |
| `POST /admin/announcements` | admin | Create; body: message, tone, audience, link?, dismissible, startsAt?, `ttl` (`{ preset: 1h\|1d\|7d\|30d }` or `{ until }`) → server computes `expiresAt` |
| `PATCH /admin/announcements/{id}` | admin | Edit (If-Match; 428 without); `ttl` may be resent to extend/shorten |
| `DELETE /admin/announcements/{id}` | admin | End now (If-Match) |
| `GET /announcements/stream?app=…` (WebSocket) | as the list | §4.4 |

Errors: 422 `MESSAGE_TOO_LONG`, `LINK_NOT_ALLOWED`, `TTL_OUT_OF_RANGE`, `STARTS_AFTER_EXPIRY`; 404; 409 version mismatch; 403 `MFA_REQUIRED` as usual for admins. Strict bodies. Every write is audited.

### 4.3 Fan-out across processes

1. The admin write commits in Mongo (source of truth).
2. catalog-svc then `PUBLISH cat:ann:changed {id}` on Redis (fire-and-forget; Redis ACL for `svc_catalog` gains the channel `cat:ann:*`; `catalog-push` gets subscribe-only).
3. Every `catalog-push` worker is subscribed; on a message it **re-reads the live set from Mongo** and sends each socket the difference for its app.
4. **Reconcile tick every 30 s** per worker: re-read the live set and push differences. This one loop also handles expiry (`remove` within ≤ 30 s, and the client hides it at `expiresAt` anyway), scheduled starts, and a lost pub/sub message (Redis restart). Cost: one indexed query per worker per 30 s.

No Kafka topic: this stays inside one service (TAD: Kafka is for service-to-service). If another service ever needs it, add `catalog.announcement.*` events through the outbox then.

### 4.4 WebSocket protocol (documented in AsyncAPI 3.0 with the `ws` binding: `docs/api/push.asyncapi.yaml`)

Path `/api/catalog/v1/announcements/stream?app=shop|sia`. Server → client JSON only:

```
{ "type": "snapshot", "items": [Announcement…], "serverTime": "…" }   on connect
{ "type": "upsert",   "item": Announcement }                           created / edited / scheduled one starts
{ "type": "remove",   "id": "ANN…" }                                   deleted / expired
{ "type": "ping" }                                                     every 25 s
```

Client frames are ignored; any frame > 1 KB closes the socket (1009). Handshake checks: **`Origin` must be the SHOP or SIA origin** (cross-site WebSocket hijacking, 403); `app=sia` needs a valid staff access cookie (py-common `cookie_values`, revocation checked) and the server closes with **4401 at the token's expiry**, the client refreshes and reconnects. Limits: per worker at most N sockets (env `PUSH_MAX_SOCKETS`, default 5,000) → close 1013 "try again later" (client falls back to polling); nginx `limit_conn` 20 per IP on this path.

### 4.5 Edge and config

- `deploy/nginx`: a `location = /api/catalog/v1/announcements/stream` → `catalog-push` with `proxy_http_version 1.1`, `Upgrade`/`Connection "upgrade"` (map), `proxy_read_timeout 75s` (> ping), `proxy_buffering off`, `limit_conn`; `test-config.sh` covers it. CSP: `connect-src 'self' wss://$host`.
- `compose.prod.yml` / `compose.dev.yml` / staging-lite: `catalog-push` (same image, `gunicorn … -k uvicorn.workers.UvicornWorker -w 1`, `mem_limit` 256m; memory budget +256 MB, INFRASTRUCTURE §4). Prometheus: `push_sockets{app}`, `push_messages_total`, alert if sockets hit 90 % of the cap.
- Staging-lite: the shared `printit-nginx` edge site file (`cimh-stores-staging.conf`) and `sia-gateway` both need the upgrade headers; `nginx -t` before reload (CLAUDE.md).
- Dev: Vite proxy entry with `ws: true` for SHOP 15173 / SIA 15174.

### 4.6 Screens

**Banner (web-app `AnnouncementBar.vue` + `useAnnouncements(app)`), in both shells above the app bar, every page incl. sign-in and 404:**
- First paint from `GET /announcements` (so a reload shows it at once), then the socket; reconnect with backoff 1 s → 30 s + jitter, pause while the tab is hidden, resync on return; after 3 failed connects poll the list every 2 min until a socket works.
- Hides each item at `expiresAt` by itself (using `serverTime` to correct the clock).
- A Vuetify layout item (so the app bar and drawer move down, nothing covered); full width, 40 px min, text wraps to 2 lines then "More".
- Tones (never colour alone): **Information** = primary wash, info icon, word "Information" for screen readers; **Alert** = warning tone, warning icon, word "Alert". SHOP in the SHOP world, SIA on Graphite Console tokens.
- Link: site paths open in place (router), external `https://` opens a new tab with `rel="noopener"`.
- Close (information only): remembered per message + `version` in `localStorage` (try/catch).
- Screen readers: messages arriving live are announced (`role="status"`, alerts `role="alert"`); ones already there at load are not.
- Arrival slides down 180 ms, leaving collapses; reduced motion = fade.

**SIA `/admin/announcements` (new A-22), Graphite Console, like Organisations:**
- List (Live · Scheduled, with tone, audience, "ends in 3 days") beside the editor (`?open=<id>` / `?open=new`).
- Editor: message with a 280 counter, tone as a segmented choice, audience (SHOP · SIA · Both), link label + URL, Show from (`DateField` + time), **Keep for** segmented presets 1 hour · 1 day · 1 week · 30 days · Until… (`DateField`), Closable switch (locked off for alerts), a **live preview** of the bar as SHOP and SIA show it.
- **Publish** asks first ("Visible to everyone on SHOP now, until 30 Nov 14:00"); **End now** asks first (red). Save bar per the forms rules (submit, then mark).
- Admin overview (A-00) lists live announcements; drawer item "Announcements" under Admin.

## 5. Tests

- catalog-svc unit: validation (length, link rules, TTL range, ALERT not closable), `expiresAt` maths, live filter, audit entries; generated authz matrix for the 5 REST routes; Schemathesis.
- Push unit (Starlette `TestClient.websocket_connect`): snapshot on connect, upsert/remove after a write, reconcile removes an expired one, wrong Origin refused, `app=sia` without/with a staff cookie, close at token expiry, socket cap → 1013, oversize frame → 1009.
- Integration (real Mongo + Redis): TTL index exists with `expireAfterSeconds: 0`; pub/sub reaches two push workers; validator refuses bad documents.
- `deploy/nginx/test-config.sh`: upgrade on the stream path, refused elsewhere.
- Playwright `announcements.spec.ts`: admin publishes → an **already open** SHOP page (second browser context) shows it without reload; reload keeps it; signed-out visitor sees it; edit updates in place; information closes and stays closed; alert has no close; End now removes it everywhere; short TTL (set via API) disappears on its own; SIA-only message absent on SHOP. axe on the bar (both tones, light/dark, 360 px) and on A-22.

## 6. Delivery

| PR | Branch | Contents |
|---|---|---|
| A | `feat/announcements-api` | Contract (OpenAPI + push AsyncAPI, validated), collection + validator + TTL index, REST + audit, `catalog-push` + Redis fan-out + reconcile, nginx/compose/Redis ACL/Prometheus, tests |
| B | `feat/announcements-screens` | `AnnouncementBar` in both shells, A-22 editor + A-00 entry, Vite ws proxy, Playwright + axe, docs + manual |

Rough size: A about 3–4 days, B about 3 days, with Claude Code. Staging deploy needs the shared edge change made by hand (owner present, `nginx -t`).

## 7. Risks

- **Many idle sockets** (1M registered users, but concurrent visitors are far fewer): capped per worker, polling fallback, separate container (D9); measured in the P9 style with k6 WebSocket (e.g. 5,000 sockets, memory per socket).
- **Corporate proxies or networks that block WebSockets**: polling fallback keeps banners working, at up to 2 min delay.
- **TTL lag**: Mongo deletes up to ~60 s late; every read filters, the client hides on time, reconcile removes within 30 s.
- **Shared staging edge**: a bad reload blips other sites; `nginx -t` first.
- **Content mistakes go to everyone at once**: confirm dialog with preview; End now is one click; everything audited.

## 8. Out of scope

Email or SIA Mobile delivery (D10); per-organisation or per-user targeting; read receipts; rich text and images; translations; using the socket for anything else (it is built so request/stock updates could be added later, not now).

## 9. Docs to update (with the PR that changes them)

PRD new story N-x (announcements) · TRD (TR for real-time push, limits) · TAD §5 catalog row + new `catalog-push`, Redis use, §7 sequence, **ADR 0016 "Server push over WebSocket from catalog-push"** · BSD §5.12 `announcements`, §3 access matrix, §7 validator, §8 retention · API README (catalogue, error codes, WebSocket conventions) + `push.asyncapi.yaml` · APD A-22, A-00, shells §2 (banner on every page) · Design Brief (banner component, tones) · SECURITY (T-xx: cross-site WebSocket hijacking, connection exhaustion, message injection; controls above) · INFRASTRUCTURE (container, memory, nginx, Redis ACL) · TEST_STRATEGY RTM · manual ch. 04/06/10/11/14 + one `sequence()` diagram (admin publish → Redis → push → browser) · CLAUDE.md.
