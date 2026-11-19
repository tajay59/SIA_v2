# ADR-0014: Carts stored in `orders` with `status: CART`

- Status: Accepted (implemented in P5, 2026-11-08; was Proposed)
- Related: BSD §5 (orders), MIGRATION_PLAN M06, ADR-0003

## Context
Legacy keeps the cart inside `accounts.cart` (identity's collection), but carts belong to order-svc (lines, Pro Bono limits, the split at submission).

## Options
1. **Leave carts on the account**: order-svc would write identity's collection, breaking ADR-0003.
2. **A new `carts` collection**: clean, but a new collection and a copy step at submission.
3. **Carts as order documents with `status: CART`**: submitting turns the cart into a request in place.

## Decision
Option 3. One cart per user, enforced by a sparse unique index on `cartOf`. A mixed cart is split into a PAID and a PROBONO request at submission. Carts inactive for 180 days are emptied (order-jobs). A suspended customer's cart is `blocked` (403 `ACCOUNT_SUSPENDED`).

## Consequences
- Every request query excludes `CART` (counts, staff queues, reports).
- The state machine starts at CART → SUBMITTED (`tests/transitions/`).
- mongomock ignores partial indexes, so cart uniqueness is tested against a real MongoDB.
