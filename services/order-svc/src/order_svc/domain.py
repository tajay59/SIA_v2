"""Pure order rules: status machines (TAD §7.2, tests/transitions/request_*.yaml), money, quote maths.

No I/O here, so every rule is unit-testable. The YAML tables are the test oracle; `TRANSITIONS` must match
them exactly (tests/test_transitions.py compares both ways).
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from bson.decimal128 import Decimal128

PAID, PROBONO = "PAID", "PROBONO"
CART = "CART"
CIMH, SUPPLIER = "CIMH", "SUPPLIER"
# Carriers (plan D5). OTHER = a carrier with no template: staff paste the tracking link (https only).
CARRIERS = ("FEDEX", "DHL", "UPS", "HAND", "OTHER")
TRACKING_URLS = {
    "FEDEX": "https://www.fedex.com/fedextrack/?trknbr={}",
    "DHL": "https://www.dhl.com/global-en/home/tracking/tracking-express.html?tracking-id={}",
    "UPS": "https://www.ups.com/track?tracknum={}",
}

# (type, from, to) -> (action, who). who: "staff" = staff or admin; "requester" = the requester or an admin;
# "any" = requester, staff or admin; "system" = jobs/consumers only.
TRANSITIONS: dict[tuple[str, str, str], tuple[str, str]] = {
    (PAID, "SUBMITTED", "QUOTING"): ("start-quoting", "staff"),
    (PAID, "SUBMITTED", "CANCELLED"): ("cancel", "any"),
    (PAID, "QUOTING", "QUOTED"): ("send-quote", "staff"),
    (PAID, "QUOTING", "CANCELLED"): ("cancel", "any"),
    (PAID, "QUOTED", "QUOTED"): ("send-quote", "staff"),
    (PAID, "QUOTED", "ACCEPTED"): ("accept", "requester"),
    (PAID, "QUOTED", "DECLINED"): ("decline", "requester"),
    (PAID, "QUOTED", "CANCELLED"): ("expire", "system"),
    (PAID, "ACCEPTED", "QUOTED"): ("reject-agreement", "staff"),
    (PAID, "ACCEPTED", "PURCHASING"): ("purchase", "staff"),
    (PAID, "ACCEPTED", "CANCELLED"): ("cancel", "staff"),
    (PAID, "DECLINED", "CANCELLED"): ("close", "system"),
    (PAID, "PURCHASING", "SHIPPED"): ("ship", "staff"),
    (PAID, "SHIPPED", "DELIVERED"): ("deliver", "staff"),
    (PROBONO, "SUBMITTED", "APPROVED"): ("approve", "staff"),
    (PROBONO, "SUBMITTED", "REJECTED"): ("reject", "staff"),
    (PROBONO, "SUBMITTED", "CANCELLED"): ("cancel", "any"),
    (PROBONO, "APPROVED", "PICKING"): ("start-picking", "staff"),
    (PROBONO, "APPROVED", "CANCELLED"): ("cancel", "staff"),
    (PROBONO, "PICKING", "SHIPPED"): ("ship", "staff"),
    (PROBONO, "SHIPPED", "DELIVERED"): ("deliver", "staff"),
}

# Statuses where the quote clock runs (expiry job; accept refuses an expired quote). "View and sign" (2026-11-17):
# QUOTED is the only one; the agreement comes with the quote, so there is no separate waiting status.
QUOTE_LIVE = ("QUOTED",)
# A rejected signature leaves the customer at least this long to upload a correct copy.
RESIGN_DAYS = 7


def legal(order_type: str, src: str, dst: str) -> tuple[str, str] | None:
    return TRANSITIONS.get((order_type, src, dst))


def sources(order_type: str, action: str) -> dict[str, str]:
    """{from: to} for an action of this request type."""
    return {s: d for (t, s, d), (a, _) in TRANSITIONS.items() if t == order_type and a == action}


def who_may(order_type: str, src: str, dst: str) -> str | None:
    found = legal(order_type, src, dst)
    return found[1] if found else None


# ---------------------------------------------------------------- money (BSD §4: Decimal128, 2 decimals)

CENT = Decimal("0.01")


def money(value: Any) -> Decimal:
    """Decimal from a Money string, Decimal128, int or Decimal, rounded half-up to cents."""
    if isinstance(value, Decimal128):
        value = value.to_decimal()
    try:
        d = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"not an amount: {value!r}") from exc
    return d.quantize(CENT, rounding=ROUND_HALF_UP)


def to_db(value: Decimal) -> Decimal128:
    return Decimal128(money(value))


def money_str(value: Any) -> str | None:
    if value is None:
        return None
    return f"{money(value):.2f}"


def rate(value: Any) -> Decimal:
    if isinstance(value, Decimal128):
        value = value.to_decimal()
    d = Decimal(str(value))
    if d <= 0:
        raise ValueError("exchange rate must be positive")
    return d


def convert_bbd(amount_bbd: Decimal, currency: str, exchange_rate: Decimal | None) -> Decimal:
    """BBD amount in the request currency. USD = BBD / rate (rate = BBD per 1 USD)."""
    if currency == "BBD":
        return money(amount_bbd)
    if exchange_rate is None:
        raise ValueError("exchange rate required")
    return money(amount_bbd / exchange_rate)


def usd_to_bbd(amount_usd: Decimal, exchange_rate: Decimal) -> Decimal:
    """A supplier's USD price in BBD (rate = BBD per 1 USD), rounded to cents."""
    return money(amount_usd * exchange_rate)


def line_source(line: dict[str, Any]) -> str | None:
    """CIMH / SUPPLIER for a paid line once quoted. Requests written before 2026-11-17 call it `choice`."""
    value = line.get("source") or line.get("choice")
    return value if value in (CIMH, SUPPLIER) else None


def tracking_url(carrier: str | None, tracking: str | None, link: str | None = None) -> str | None:
    """The customer's Track link: a carrier template, or for OTHER the https link staff entered."""
    if carrier == "OTHER":
        return link if link and link.startswith("https://") else None
    if not carrier or not tracking or carrier not in TRACKING_URLS:
        return None
    from urllib.parse import quote

    return TRACKING_URLS[carrier].format(quote(tracking, safe=""))
