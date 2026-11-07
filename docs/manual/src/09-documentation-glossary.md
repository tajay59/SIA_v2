# 9. Documentation map and glossary

[← Technology stack](08-technology-stack.md) · [Manual home](README.md) · [Next: API →](10-api.md)

## 9.1 How the documents relate

![Documentation map](images/23-documentation-map.svg)

| Document | Definition | Status |
|---|---|---|
| [PRD](../PRD.md): Product Requirements Document | What the product does, feature by feature; expected functionality and behaviour (Atlassian structure) | Draft |
| [TRD](../TRD.md): Technical Requirements Document | Tools, techniques and infrastructure; numeric technical requirements | Draft |
| [TAD](../TAD.md): Technical Architecture Document | How the system is built: parts, connections and reasons | Draft |
| [BSD](../BSD.md): Background (Backend) Schema Document | Where data lives, its structure, who can access it, relationships | Draft |
| [API Specification](../api/README.md) | Exact contract for every endpoint and event | Draft (validated) |
| [APD](../APD.md): App Flow Document | What happens on each click; which page comes next; main user journeys | Draft |
| [Design Brief](../DESIGN_BRIEF.md) | Visual direction: colours, fonts, how each screen should look | Draft |
| [Security and Threat Model](../SECURITY.md) | Assets, threats (STRIDE), controls, secrets, privacy, security testing | Draft |
| [Data Migration Plan](../MIGRATION_PLAN.md) | Moving legacy data into v2: mapping, checks, dry runs, cut-over, rollback | Draft |
| [Infrastructure and Environment Plan](../INFRASTRUCTURE.md) | Machines, network, containers, environments, provisioning | Draft |
| [Test Strategy](../TEST_STRATEGY.md) | How quality is proved: levels, tools, gates, criteria | Draft |
| [Implementation Plan](../IMPLEMENTATION_PLAN.md) | What gets built, in what order; phases and deliverables | Draft |

The full list of 32 documents, covering before, during and after the build, is in the [Documentation Index](../DOCUMENTATION_INDEX.md).

## 9.2 Architecture decisions (ADRs)

| ADR | Decision | Status |
|---|---|---|
| 0001 | Microservices split by business area | Accepted |
| 0002 | FastAPI + Python | Accepted |
| 0003 | MongoDB; one `inventory` database; existing names; one owner per collection | Accepted |
| 0004 | Replica set: host primary + 2 Pi 5 secondaries | Accepted |
| 0005 | Kafka for events; HTTP only for immediate questions | Accepted |
| 0006 | Outbox saved on the changed document + change-stream relay | Accepted |
| 0007 | EdDSA tokens, JWKS, Redis revocation | Accepted |
| 0008 | Local file volume + X-Accel-Redirect | Accepted |
| 0009 | Docker Compose only | Accepted |
| 0010 | Vue 3 + TS + Vuetify 4 + file-based routing + Zod 4 | Accepted |
| 0011 | Prometheus + Alertmanager only | Accepted |
| 0012 | Sites/shelves stay in `misc` for now | Proposed |
| 0013 | Single application host | Accepted |
| 0014 | Carts stored in `orders` (`status: CART`) | Proposed |
| 0015 | Quote → accept replaces online payment | Accepted |

## 9.3 Glossary

| Term | Meaning |
|---|---|
| **APD** | App Flow Document |
| **BBD / USD** | Barbados dollar / US dollar: the only quote currencies |
| **BSD** | Background (Backend) Schema Document |
| **CIMH stock quote** | Generated quote offering lines fully available in CIMH stock (catalogue cost + admin fee) |
| **Circuit breaker** | Stops calling a failing service for a short time so failures don't cascade |
| **Consumer group** | Set of replicas of one service that share a Kafka topic's partitions |
| **DLQ** | Dead-letter queue: where messages go after all retries fail |
| **EdDSA / Ed25519** | Signature algorithm used for tokens |
| **Idempotent** | Safe to apply more than once with the same result |
| **IDOR** | Insecure Direct Object Reference: reading someone else's data by changing an id |
| **JWKS** | JSON Web Key Set: public keys used to verify tokens |
| **KRaft** | Kafka's built-in cluster coordination (no ZooKeeper) |
| **Pro Bono** | Pro Bono item: free item from CIMH stock; no quote |
| **Outbox** | Events saved with the state change, then published by a relay |
| **Primary / secondary** | The MongoDB member that accepts writes / members that keep copies |
| **RPO / RTO** | Maximum data loss / maximum time to restore |
| **Cut-over** | The single maintenance window in which production data moves from legacy to v2 and traffic switches |
| **TTL index** | MongoDB index that deletes documents automatically after a time |
| **X-Accel-Redirect** | nginx header that serves an internal file after the app approves it |
