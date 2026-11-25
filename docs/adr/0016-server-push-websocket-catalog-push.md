# ADR-0016: Server push over a WebSocket from `catalog-push`

- Status: Accepted (owner, 2026-11-23; built the same day)
- Related: plan `docs/plans/2026-11-23-announcements.md` (D1, D9), PRD N4, BSD §5.12, API `push.asyncapi.yaml`, ADR-0005 (Kafka between services), ADR-0011

## Context
Admins post announcements that must appear on every open SHOP and SIA page at once, without a reload, and stay after a reload. Until now nothing in the platform pushed to browsers: every screen polled or reloaded. SHOP must reach signed-out visitors too, so the channel can't depend on a session, and the host's memory budget is tight (INFRASTRUCTURE §4).

## Options
1. **Polling** `GET /announcements` every 30–60 s: no new moving parts, but never "at once" and 1M visitors × polls is load for nothing.
2. **Server-Sent Events**: one-way by design, plain HTTP, browser reconnects on its own; simpler for a banner.
3. **WebSocket** (owner's ask): one socket per tab; needs the upgrade at nginx and an Origin check, and reconnect logic in the client.

Where it runs:
- a. inside catalog-svc's existing workers;
- b. **a separate `catalog-push` container from the catalog-svc image** (only the stream and the live list).

Fan-out between processes:
- i. Kafka topic + a consumer group per worker;
- ii. **Redis pub/sub** poke + re-read from MongoDB, plus a periodic reconcile.

## Decision
Option 3 with b and ii. The browser first reads `GET /announcements` (a reload shows the banner at once), then opens `/api/catalog/v1/announcements/stream`: `snapshot` on connect, `upsert` / `remove` on change, `ping` every 25 s. A write in catalog-svc publishes `cat:ann:changed` on Redis; every catalog-push worker re-reads the live set from MongoDB (the source of truth) and sends each socket its difference; a reconcile tick (30 s; 10 s in dev) does the same, which also covers expiry, scheduled starts and a lost pub/sub message. No Kafka: the change never leaves catalog's ownership (ADR-0005 is for service-to-service). Origin must be SHOP/SIA; `app=sia` needs the staff cookie and is closed (4401) when the access token expires; sockets are capped per worker (`PUSH_MAX_SOCKETS`, 1013 → the client polls every 2 min) and per address at nginx (`limit_conn 20`).

## Consequences
- One more container (256 MB in production, alert `PushSocketsNearCap` at 90 % of the cap); scale with replicas.
- nginx (production, staging gateway and the shared staging edge) passes the upgrade on one exact path; CSP gains `connect-src 'self' wss://<host>`.
- Redis ACL: the catalog user gets `&cat:ann:*` with publish/subscribe (first pub/sub use in the platform).
- Delivery is at most once while connected; correctness comes from the snapshot on every (re)connect and the reconcile tick, so a client is never more than one reconnect or one tick behind.
- The same channel could carry other live updates later; it carries announcements only today.
