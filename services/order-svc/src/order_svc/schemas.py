"""`$jsonSchema` validators for order-svc's collection (BSD §7 example); applied at start-up."""

from cimh_common.validation import ARRAY, DATE, ID, MONEY, STRING, VERSION, document, enum, nullable

STATUSES = enum(
    "CART", "SUBMITTED", "QUOTING", "QUOTED", "ACCEPTED", "DECLINED", "PURCHASING",
    "APPROVED", "REJECTED", "PICKING", "SHIPPED", "DELIVERED", "CANCELLED",
)  # fmt: skip

LINE = document({"productId": ID, "qty": {"bsonType": ["int", "long"], "minimum": 1}}, {"lineId": STRING})

# The current invoice of one kind (plan 2026-11-24-invoice-crud). Upgraded legacy records have no number or lines.
INVOICE = document(
    {"rev": VERSION, "fileId": ID, "revisions": ARRAY},
    {
        "number": nullable(STRING),
        "total": MONEY,
        "lines": nullable(ARRAY),
        "date": nullable(DATE),
        "source": enum("STAFF", "AUTO", "LEGACY"),
    },
)

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
        {
            "type": enum("PAID", "PROBONO", None),
            "currency": enum("BBD", "USD", None),
            # No `required` here: MongoDB refuses an empty one.
            "invoices": {"bsonType": "object", "properties": {"invoice": INVOICE, "commercial_invoice": INVOICE}},
            "invoicesVoided": ARRAY,
            "invoiceNumbers": {**ARRAY, "items": STRING},
        },
    ),
}
