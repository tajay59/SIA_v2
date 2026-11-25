"""Collections owned by catalog-svc (BSD §5.5-5.7, §5.12): `product`, the `xuser` view, `misc`, `announcements`."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from catalog_svc.schemas import SCHEMAS
from cimh_common.validation import apply_validators

# Customer-facing fields (ProductPublic). The `xuser` view and every public API answer use THIS list, so the
# view, the API and the snapshot tests can't drift apart (BSD §5.6).
PUBLIC_FIELDS: tuple[str, ...] = (
    "id",
    "name",
    "description",
    "details",
    "make",
    "modelname",
    "modelnumber",
    "type",
    "department",
    "project",
    "probono",
    "probonoMaxPerRequest",
    "unitquantity",
    "weight",
    "dimension",
    "images",
    "inStock",
)
# SHOP shows only meteorological and radar items, plus Pro Bono items of any type (owner, 2026-11-16).
# Staff views ignore this; it binds every customer/anonymous answer and the `xuser` view.
SHOP_TYPES = ("MET", "RAD")
PUBLIC_FILTER: dict[str, Any] = {
    "sellable": True,
    "active": True,
    "$or": [{"type": {"$in": list(SHOP_TYPES)}}, {"probono": True}],
}


def public_filter(filters: dict[str, Any]) -> dict[str, Any]:
    """PUBLIC_FILTER for a customer query, without the `$or` when the query names a type (TR-DATA-5: the `$or`
    made type-filtered lists sort in memory and type-filtered search examine every text match).
    MET/RAD: plain type match. Any other type: only its Pro Bono items. No type: the full `$or`.
    Callers apply their own `type`/`probono` filters first; this result is merged last and wins."""
    t = filters.get("type")
    if not t:
        return dict(PUBLIC_FILTER)
    base = {"sellable": True, "active": True, "type": t}
    if t in SHOP_TYPES:
        return base
    # Other types are visible only as Pro Bono; asking for non-Pro Bono items of such a type finds nothing.
    return {**base, "probono": {"$in": []} if filters.get("probono") is False else True}


XUSER_PIPELINE: list[dict[str, Any]] = [
    {"$match": PUBLIC_FILTER},
    {"$project": {"_id": 0, **dict.fromkeys(PUBLIC_FIELDS, 1)}},
]

TEXT_WEIGHTS = {"name": 10, "modelnumber": 8, "keywords": 5, "make": 3, "modelname": 3}


def now() -> datetime:
    return datetime.now(UTC)


class Store:
    def __init__(self, db: Any) -> None:
        self.db = db
        self.product = db["product"]
        self.misc = db["misc"]
        self.announcements = db["announcements"]

    async def ensure_indexes(self) -> None:
        # BSD §7 validators first: the collections exist with their schema before any index or write.
        await apply_validators(self.db, SCHEMAS)
        p = self.product
        await p.create_index("id", unique=True)
        await p.create_index(
            [(f, "text") for f in TEXT_WEIGHTS], weights=TEXT_WEIGHTS, name="product_text", default_language="english"
        )
        # Browsing is sorted by name with the id as tie-breaker (cursor paging). Each filter combination the
        # screens use has an index whose equality prefix is followed by (name, id), so no list sorts in memory
        # (checked on 200k products by tools/perf/explain_catalog.py).
        await p.create_index([("sellable", 1), ("active", 1), ("type", 1), ("department", 1), ("name", 1), ("id", 1)])
        await p.create_index([("sellable", 1), ("active", 1), ("type", 1), ("name", 1), ("id", 1)])
        await p.create_index([("sellable", 1), ("active", 1), ("name", 1), ("id", 1)])
        await p.create_index([("probono", 1), ("active", 1), ("type", 1), ("name", 1), ("id", 1)])
        await p.create_index([("active", 1), ("type", 1), ("name", 1), ("id", 1)])
        await p.create_index([("active", 1), ("name", 1), ("id", 1)])
        await p.create_index([("type", 1), ("name", 1), ("id", 1)])  # staff "show inactive" by type
        await p.create_index([("name", 1), ("id", 1)])  # staff "show inactive"
        await p.create_index("sn", sparse=True)
        await p.create_index("sn1", sparse=True)
        await p.create_index("modelnumber")
        await p.create_index([("outbox.0", 1)], sparse=True)
        await self.misc.create_index("id", unique=True)
        await self.misc.create_index([("kind", 1), ("site", 1), ("location", 1)])
        await self.misc.create_index([("kind", 1), ("id", 1)])  # places list, sorted by (kind, id)
        await self.misc.create_index([("outbox.0", 1)], sparse=True)
        a = self.announcements
        await a.create_index("id", unique=True)
        # TTL: MongoDB deletes a message once `expiresAt` has passed (the monitor runs about once a minute).
        await a.create_index("expiresAt", expireAfterSeconds=0, name="announcement_ttl")
        await a.create_index([("audience", 1), ("startsAt", 1)])

    async def ensure_view(self) -> None:
        """Create or redefine `xuser` (real MongoDB only; the mock has no views)."""
        names = await self.db.list_collection_names(filter={"name": "xuser"})
        if names:
            await self.db.command({"collMod": "xuser", "viewOn": "product", "pipeline": XUSER_PIPELINE})
        else:
            await self.db.create_collection("xuser", viewOn="product", pipeline=XUSER_PIPELINE)
