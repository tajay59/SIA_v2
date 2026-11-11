"""Collections owned by identity-svc (BSD §5.1-5.4) and their indexes."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from cimh_common.ids import ulid
from cimh_common.validation import apply_validators
from identity_svc.schemas import SCHEMAS


def now() -> datetime:
    return datetime.now(UTC)


class Store:
    def __init__(self, db: Any) -> None:
        self.db = db
        self.accounts = db["accounts"]
        self.temp = db["temp"]
        self.organisations = db["organisations"]
        self.audit = db["auditlog"]

    async def ensure_indexes(self) -> None:
        # BSD §7 validators first: the collections exist with their schema before any index or write.
        await apply_validators(self.db, SCHEMAS)
        await self.accounts.create_index("id", unique=True)
        await self.accounts.create_index("email", unique=True)
        await self.accounts.create_index([("status", 1), ("createdAt", 1)])
        await self.accounts.create_index([("organisationId", 1)])
        await self.accounts.create_index([("outbox.0", 1)], sparse=True)
        await self.temp.create_index("id", unique=True)
        await self.temp.create_index("expireAt", expireAfterSeconds=0)
        await self.temp.create_index([("accountId", 1), ("kind", 1)])
        await self.organisations.create_index("id", unique=True)
        await self.organisations.create_index("nameKey", unique=True)
        await self.organisations.create_index("emailDomains")
        await self.organisations.create_index("aliases")
        await self.audit.create_index("id", unique=True)
        await self.audit.create_index([("entity.type", 1), ("entity.id", 1), ("at", -1)])
        await self.audit.create_index([("actor.id", 1), ("at", -1)])
        await self.audit.create_index([("action", 1), ("at", -1)])

    async def record_audit(
        self,
        *,
        actor: dict[str, Any],
        action: str,
        entity_type: str,
        entity_id: str,
        correlation_id: str,
        before: Any = None,
        after: Any = None,
        reason: str | None = None,
        ip: str | None = None,
    ) -> None:
        """auditlog is insert-only (svc_identity has insert + find)."""
        doc: dict[str, Any] = {
            "id": "AUD" + ulid(),
            "at": now(),
            "actor": actor,
            "action": action,
            "entity": {"type": entity_type, "id": entity_id},
            "correlationId": correlation_id,
        }
        if before is not None:
            doc["from"] = before
        if after is not None:
            doc["to"] = after
        if reason:
            doc["reason"] = reason
        if ip:
            doc["ip"] = ip
        await self.audit.insert_one(doc)
