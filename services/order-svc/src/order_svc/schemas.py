"""`$jsonSchema` validators for order-svc's collection (BSD §7 example); applied at start-up."""

from cimh_common.validation import ARRAY, DATE, ID, STRING, VERSION, document, enum

STATUSES = enum(
    "CART", "SUBMITTED", "QUOTING", "QUOTED", "AWAITING_AGREEMENT", "ACCEPTED", "DECLINED", "PURCHASING",
    "APPROVED", "REJECTED", "PICKING", "SHIPPED", "DELIVERED", "CANCELLED",
)  # fmt: skip

LINE = document({"productId": ID, "qty": {"bsonType": ["int", "long"], "minimum": 1}}, {"lineId": STRING})

SCHEMAS = {
    "orders": document(
        {
            "id": ID,
            "status": STATUSES,
            "lines": {**ARRAY, "items": LINE},
            "outbox": ARRAY,
            "createdAt": DATE,
            "updatedAt": DATE,
            "version": VERSION,
        },
        {"type": enum("PAID", "PROBONO", None), "currency": enum("BBD", "USD", None)},
    ),
}
