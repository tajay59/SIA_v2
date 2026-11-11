"""`$jsonSchema` validators for catalog-svc's collections (BSD §5, §7); applied at start-up."""

from cimh_common.validation import ARRAY, BOOL, COUNT, DATE, ID, INT, MONEY, STRING, VERSION, document, enum

TYPES = enum("MET", "RAD", "EQUIP", "SUPP", "MISC", "PRO")
MISC_KINDS = enum(
    "counter", "departments", "location", "projects", "shelf", "site", "types", "settings", "fees", "emailLists"
)

SCHEMAS = {
    "product": document(
        {
            "id": ID,
            "number": INT,
            "name": STRING,
            "type": TYPES,
            "department": STRING,
            "sellable": BOOL,
            "probono": BOOL,
            "active": BOOL,
            "threshold": COUNT,
            "images": ARRAY,
            "keywords": ARRAY,
            "outbox": ARRAY,
            "createdAt": DATE,
            "updatedAt": DATE,
            "version": VERSION,
        },
        # Money is Decimal128, never a string (a seeding tool wrote strings until 2026-11-10).
        {"cost": MONEY, "inStock": BOOL},
    ),
    "misc": document({"id": ID, "kind": MISC_KINDS, "updatedAt": DATE}),
}
