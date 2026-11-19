# ADR-0003: MongoDB kept; one database; each collection owned by one service

- Status: Accepted (2026-11-06)
- Related: BSD §3, §5, §7; TAD §6.1; ADR-0001

## Context
The legacy data lives in MongoDB database `inventory` (accounts, product, storage, history, orders, misc, temp). PRD §4 requires MongoDB and keeping the existing collection names, which keeps the migration a mapping exercise (MIGRATION_PLAN §5) rather than a redesign.

## Options
1. **Database per service** (several databases or clusters): strongest isolation; renames every collection and multiplies clusters on limited hardware.
2. **One database, collections owned by one service each**: same names, one replica set, ownership enforced by MongoDB roles.
3. **Shared database, any service reads anything**: what legacy did; couples every service to every schema.

## Decision
Option 2. One database `inventory`. Ownership: identity (`accounts`, `temp`, `organisations`, `auditlog`), catalog (`product`, `xuser` view, `misc`), inventory (`storage`, `history`, `stock`), order (`orders`, carts included, ADR-0014). Each service's Mongo user may only touch its own collections (`deploy/mongo/roles.js`). Transactions are allowed within a service.

## Consequences
- Another service's data is reached only by API or events; copies (e.g. names on a request) are snapshots updated by events.
- Each service applies its own `$jsonSchema` validators at start-up (`<service>/schemas.py`, BSD §7), strict by default.
- One replica set to run and back up (ADR-0004).
- A service can't join across ownership lines; reports needing several areas are built from events or API calls.
