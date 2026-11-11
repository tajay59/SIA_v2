"""`$jsonSchema` validators for identity-svc's collections (BSD §5, §7); applied at start-up."""

from cimh_common.validation import ARRAY, BOOL, DATE, ID, INT, OBJECT, STRING, VERSION, document, enum, nullable

ROLES = enum("admin", "staff", "user")
STATUSES = enum("PENDING_VERIFICATION", "PENDING_APPROVAL", "ACTIVE", "REJECTED", "SUSPENDED", "EXPIRED")

SCHEMAS = {
    "accounts": document(
        {
            "id": ID,
            "email": STRING,
            "firstname": STRING,
            "lastname": STRING,
            "role": ROLES,
            "status": STATUSES,
            "isCimh": BOOL,
            "statusHistory": ARRAY,
            "outbox": ARRAY,
            "createdAt": DATE,
            "updatedAt": DATE,
            "version": VERSION,
        },
        # passwordHash is removed when an account is erased (BSD §8), so it is typed, not required.
        {
            "organisationId": nullable(STRING),
            "organisationText": nullable(STRING),
            "mfa": OBJECT,
            "passwordHash": STRING,
        },
    ),
    # Email codes (hash + sealed copy; never the plain code). TTL index on expireAt.
    "temp": document(
        {
            "id": ID,
            "kind": STRING,
            "accountId": ID,
            "codeHash": STRING,
            "attempts": INT,
            "createdAt": DATE,
            "expireAt": DATE,
        }
    ),
    "organisations": document(
        {
            "id": ID,
            "name": STRING,
            "nameKey": STRING,
            "country": STRING,
            "active": BOOL,
            "aliases": ARRAY,
            "emailDomains": ARRAY,
            "createdAt": DATE,
            "updatedAt": DATE,
            "version": VERSION,
        },
        {"type": nullable(STRING), "mergedInto": nullable(STRING)},
    ),
    "auditlog": document({"id": ID, "action": STRING, "actor": OBJECT, "entity": OBJECT, "at": DATE}),
}
