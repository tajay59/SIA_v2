# ADR-0015: Quote → view and sign instead of online payment

- Status: Accepted (2026-11-06; amended 2026-11-17 "view and sign")
- Related: PRD O3–O8, TAD §7.2, `docs/plans/2026-11-17-view-and-sign.md`, ADR-0005

## Context
CIMH supplies equipment to member organisations, invoices them, and often buys from suppliers on their behalf. Nobody pays by card; organisations need a formal quote and a signed agreement before CIMH spends money.

## Options
1. **Online payment (card gateway)**: doesn't match how member organisations pay; brings PCI scope.
2. **Quote → customer chooses options per line → signs** (the 2026-11-06 design, with `AWAITING_AGREEMENT`).
3. **Quote → customer views and signs, or cancels**; staff fix one source per line.

## Decision
Option 3 (owner, 2026-11-17; replaces option 2). Flow: SUBMITTED → QUOTING → QUOTED → ACCEPTED → PURCHASING → SHIPPED → DELIVERED (declined or expired → CANCELLED). Staff fix each line's source (CIMH stock only when it covers the full quantity, otherwise one supplier) and estimated shipping per source. Sending the quote reserves CIMH stock and generates the agreement PDF. The customer uploads the signed copy (stamped with the quote version) or cancels; staff verify the signature before purchase orders. Quotes are in BBD and valid 30 days; the admin fee is charged once per request. Pro Bono items skip the quote (SUBMITTED → APPROVED → PICKING → SHIPPED → DELIVERED). Shipping is recorded per parcel with a manually entered tracking number; no carrier APIs.

## Consequences
- No payment data and no PCI scope; the signed total is what CIMH invoices.
- `AWAITING_AGREEMENT` is gone; order-svc moves old ones to QUOTED at start-up.
- A revised quote voids the agreement and any signed copy; reservations are swapped in one transaction.
