"""Collections owned by inventory-svc (BSD §5.8-5.9, §5.11): `storage`, `history`, `stock`."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, TypeVar

from cimh_common.validation import apply_validators
from inventory_svc.schemas import SCHEMAS

T = TypeVar("T")

# A unit is available when it is on a shelf, not picked and not reserved (BSD §5.8). `reservedFor: None`
# also matches documents without the field (v2 removes it on release).
AVAILABLE: dict[str, Any] = {"stowed": True, "picked": False, "reservedFor": None}
# Partial indexes: only units that actually carry the value are indexed (most of 30M units carry none).
SET = {"$gt": ""}


def now() -> datetime:
    return datetime.now(UTC)


class Store:
    def __init__(self, db: Any) -> None:
        self.db = db
        self.storage = db["storage"]
        self.history = db["history"]
        self.stock = db["stock"]

    async def ensure_indexes(self) -> None:
        # BSD §7 validators first: the collections exist with their schema before any index or write.
        await apply_validators(self.db, SCHEMAS)
        s = self.storage
        await s.create_index("barcode", unique=True)
        await s.create_index([("product", 1), ("stowed", 1), ("picked", 1), ("reservedFor", 1)])
        await s.create_index([("shelf", 1), ("stowed", 1), ("barcode", 1)])
        await s.create_index([("location", 1), ("product", 1), ("stowed", 1)])
        await s.create_index([("reservedFor", 1)], partialFilterExpression={"reservedFor": SET})
        await s.create_index([("orderid", 1)], partialFilterExpression={"orderid": SET})
        await s.create_index([("assignedTo", 1), ("barcode", 1)], partialFilterExpression={"assignedTo": SET})
        await s.create_index([("product", 1), ("assignedTo", 1)], partialFilterExpression={"assignedTo": SET})
        h = self.history
        # Newest first with _id as tie-breaker (cursor paging over equal timestamps).
        await h.create_index([("id", 1), ("date", -1), ("_id", -1)])
        await h.create_index([("user", 1), ("date", -1), ("_id", -1)])
        await h.create_index([("date", -1), ("_id", -1)])
        st = self.stock
        await st.create_index("id", unique=True)
        await st.create_index([("low", 1), ("productName", 1), ("id", 1)])
        await st.create_index([("outbox.0", 1)], sparse=True)

    async def transaction(self, fn: Callable[[Any], Awaitable[T]]) -> T:
        """Run `fn(session)` in a multi-document transaction (TAD §7.3), retried on transient conflicts.

        On the unit-test mock (no client, no transactions) `fn(None)` runs directly; callers that can stop
        half-way also compensate, and the real race is covered by the integration tests.
        """
        client = getattr(self.db, "client", None)
        if client is None:
            return await fn(None)
        from pymongo import WriteConcern
        from pymongo.read_concern import ReadConcern

        async with client.start_session() as session:
            result: T = await session.with_transaction(
                fn, read_concern=ReadConcern("snapshot"), write_concern=WriteConcern("majority")
            )
            return result
