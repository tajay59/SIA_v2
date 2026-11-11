"""`$jsonSchema` validators for inventory-svc's collections (BSD §5, §7); applied at start-up."""

from cimh_common.validation import ARRAY, BOOL, COUNT, DATE, ID, STRING, document, enum, nullable

OPERATIONS = enum("stow", "pick", "relocate", "assign", "unassign", "reserve", "release", "adjust")

SCHEMAS = {
    "storage": document(
        {
            "barcode": ID,
            "product": ID,
            "stowed": BOOL,
            "picked": BOOL,
            "images": ARRAY,
            "createdAt": DATE,
            "updatedAt": DATE,
        },
        {
            "serial": nullable(STRING),
            "shelf": nullable(STRING),
            "assignedTo": nullable(STRING),
            "reservedFor": nullable(STRING),
        },
    ),
    "history": document({"id": ID, "operation": OPERATIONS, "user": STRING, "date": DATE}),
    # Built by partial upserts (the catalog event sets name/threshold/active, recounts set the numbers), so only
    # the id is required; every field is typed when present.
    "stock": document(
        {"id": ID},
        {
            "available": COUNT,
            "reserved": COUNT,
            "picked": COUNT,
            "assigned": COUNT,
            "threshold": COUNT,
            "low": BOOL,
            "active": BOOL,
            "productName": STRING,
            "type": STRING,
            "updatedAt": DATE,
        },
    ),
}
