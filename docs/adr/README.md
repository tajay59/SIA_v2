# Architecture Decision Records

One file per decision: context, options, decision, consequences. The summary table is TAD §11; a change to a decision updates both. New ADRs take the next number; a replaced decision is marked "Superseded by ADR-nnnn", never deleted.

| ADR | Decision | Status |
|---|---|---|
| [0001](0001-microservices-by-business-area.md) | Microservices split by business area | Accepted |
| [0002](0002-fastapi-python.md) | FastAPI + Python for all services | Accepted |
| [0003](0003-mongodb-one-database-owned-collections.md) | MongoDB; one `inventory` database; each collection owned by one service | Accepted |
| [0004](0004-replica-set-host-and-pis.md) | Replica set: primary on the host, secondaries on 2 Pi 5 | Accepted |
| [0005](0005-kafka-events-http-for-questions.md) | Kafka for events; HTTP only for immediate questions | Accepted |
| [0006](0006-outbox-on-document-relay.md) | Outbox on the changed document + relay | Accepted |
| [0007](0007-eddsa-jwt-jwks-redis-revocation.md) | EdDSA tokens via JWKS; revocation in Redis | Accepted |
| [0008](0008-local-files-x-accel-redirect.md) | Local file volume + nginx X-Accel-Redirect | Accepted |
| [0009](0009-docker-compose-only.md) | Docker Compose only | Accepted |
| [0010](0010-vue-vuetify-frontends.md) | Vue 3 + TypeScript + Vuetify 4 + file routes + Zod 4 | Accepted |
| [0011](0011-prometheus-alertmanager-only.md) | Prometheus + Alertmanager only | Accepted |
| [0012](0012-places-in-misc.md) | Places kept in `misc` (catalog-svc) | Proposed |
| [0013](0013-single-application-host.md) | Single application host | Accepted |
| [0014](0014-carts-in-orders.md) | Carts in `orders` with `status: CART` | Accepted |
| [0015](0015-quote-and-sign-no-payments.md) | Quote → view and sign, no payments | Accepted (amended 2026-11-17) |
| [0016](0016-server-push-websocket-catalog-push.md) | Server push over a WebSocket from `catalog-push` | Accepted (2026-11-23) |
