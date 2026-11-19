# ADR-0012: Sites, locations and shelves kept in `misc`, owned by catalog-svc

- Status: Proposed (review after load tests; evidence so far below)
- Related: BSD §5.7, TAD §5.2, TAD R4, ADR-0003

## Context
Legacy keeps sites and locations (shelves as arrays) in `misc`, next to settings and counters. inventory-svc must resolve a scanned shelf barcode on every stow, pick and relocate.

## Options
1. **Keep places in `misc` (catalog-svc owns it); inventory asks catalog over HTTP and caches the answer.**
2. **Move places to a new inventory-owned collection**: inventory owns what it uses most; another migration step and a split of `misc`.

## Decision
Option 1 for now. Migration splits shelves to one document each (`kind` field). inventory-svc resolves places through catalog `/internal/places?barcode=` and caches answers in Redis (`inv:place:*`).

## Consequences
- One more synchronous dependency on the scan path (catalog must be up for uncached places).
- Review evidence (2026-11-19): P3 performance (200k products, p95 43 ms) and the P9 mixes and soak passed with this design; no scan-latency issue was found. Accepting it is an owner decision; revisit if the sized-as-prod tests show catalog slowing scans.
