"""The collection owned by order-svc (BSD §5.10): `orders` (carts have status CART)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, TypeVar

from cimh_common.validation import apply_validators
from order_svc.schemas import SCHEMAS

T = TypeVar("T")


def now() -> datetime:
    return datetime.now(UTC)


class Store:
    def __init__(self, db: Any) -> None:
        self.db = db
        self.orders = db["orders"]

    async def ensure_indexes(self) -> None:
        # BSD §7 validators first: the collections exist with their schema before any index or write.
        await apply_validators(self.db, SCHEMAS)
        o = self.orders
        await o.create_index("id", unique=True)
        # One cart per user (BSD §5.10): only carts carry `cartOf` (= customer), so a sparse unique index does it
        # without a partial filter (same result, and the unit-test mock honours it).
        await o.create_index("cartOf", unique=True, sparse=True)
        await o.create_index([("customer", 1), ("submittedAt", -1), ("id", -1)])
        await o.create_index([("organisationId", 1), ("submittedAt", -1), ("id", -1)])
        await o.create_index([("status", 1), ("updatedAt", 1), ("id", 1)])
        await o.create_index([("type", 1), ("status", 1), ("submittedAt", -1)])
        await o.create_index([("submittedAt", -1), ("id", -1)])
        await o.create_index([("quoteExpiresAt", 1)], partialFilterExpression={"status": "QUOTED"})
        await o.create_index([("lines.productId", 1)])
        await o.create_index([("outbox.0", 1)], sparse=True)

    async def transaction(self, fn: Callable[[Any], Awaitable[T]]) -> T:
        """Run `fn(session)` in a multi-document transaction; on the unit-test mock it runs directly."""
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
