# ADR-0001: Microservices split by business area

- Status: Accepted (2026-11-06)
- Related: TAD §3–§4, ADR-0003, ADR-0005, ADR-0013

## Context
The legacy system is one Flask app (`views.py` ~3.7k lines) with one Mongo access layer. Every feature shares code, deploys together and was hard to secure (PRD §3). The target is up to 1M registered users and ~1,000 req/s at peak (TRD §2), built by one developer with Claude Code.

## Options
1. **Modular monolith**: one FastAPI app, modules per area, one image. Simplest to run; scaling and failure isolation are all or nothing.
2. **Microservices by business area**: identity, catalog, inventory, order, document, notification (+ media-worker). Each owns its collections and scales on its own.
3. **Finer services** (per entity, e.g. carts, quotes, labels apart). Too many deployables and contracts for one developer.

## Decision
Option 2: six services split by business area, plus the media-worker (GPU work) and one outbox relay per service. A service talks to another only through its API or its events (ADR-0005), never through its data (ADR-0003).

## Consequences
- Each area scales and fails on its own; a slow PDF render can't stall logins.
- More moving parts: contracts (`docs/api/`), a shared library (`packages/py-common`) for auth, outbox, consumers and Redis, and generated authz/IDOR tests per service.
- Cross-area work (e.g. a request reserving stock) is eventually consistent and must be designed as events (TAD §6.3).
- Everything still runs on one host (ADR-0013); the split is about ownership and isolation, not hardware.
