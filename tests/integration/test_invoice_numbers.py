"""Integration: order-svc invoice records on a real MongoDB (plan 2026-11-24-invoice-crud). mongomock can't check a
unique index on an array field, so the unit tests only exercise the service's own number check; here the index
itself refuses a number another request holds (a race past that check), and the strict validators accept every
record shape the service and the start-up upgrade write.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

pytestmark = pytest.mark.integration

ACTOR = {"id": "USRSTAFF", "name": "S Taff", "role": "staff"}


def _order(rid: str, **kw: Any) -> dict[str, Any]:
    t = datetime.now(UTC)
    return {"id": rid, "type": "PAID", "status": "DELIVERED", "customer": "USRUSER", "lines": [], "outbox": [],
            "createdAt": t, "updatedAt": t, "version": 1, **kw}  # fmt: skip


def _body(number: str, rev: int | None = None) -> dict[str, Any]:
    fid = "FIL" + uuid.uuid4().hex
    return {"rev": rev, "number": number, "date": "2026-11-24", "source": "STAFF", "by": ACTOR,
            "lines": [{"lineId": None, "description": "Rain gauge", "qty": 2, "unitPrice": "150.00"}],
            "fees": "25.00", "discount": "0.00", "shipping": "40.00",
            "file": {"id": fid, "kind": "invoice", "name": f"Invoice-{number}.pdf", "mime": "application/pdf",
                     "size": 10}}  # fmt: skip


def test_invoice_numbers_unique_across_requests_on_real_mongo(stack: Any) -> None:
    from pymongo import AsyncMongoClient
    from pymongo.errors import DuplicateKeyError

    from cimh_common.errors import ProblemError
    from order_svc import upgrade
    from order_svc.service import OrderService
    from order_svc.store import Store

    async def run() -> None:
        db = AsyncMongoClient(stack.mongo_url, tz_aware=True)[f"itest_{uuid.uuid4().hex[:8]}"]
        store = Store(db)
        await store.ensure_indexes()  # strict validators + the multikey unique index
        svc = OrderService(store, deps=None)  # type: ignore[arg-type]  # invoices use the store only
        await store.orders.insert_many([_order("ORDA"), _order("ORDB"), _order("ORDC")])  # no numbers: sparse

        out = await svc.record_invoice("ORDA", "invoice", _body("2026-014"))
        assert out["invoice"]["total"] == "365.00"
        await svc.record_invoice("ORDA", "invoice", _body("2026-015", rev=1))  # renumbered: both stay taken

        # The service refuses a taken number itself...
        with pytest.raises(ProblemError) as err:
            await svc.record_invoice("ORDB", "invoice", _body("2026-014"))
        assert err.value.code == "INVOICE_NUMBER_TAKEN"
        # ...and the index refuses it when a write gets past that check (two saves at once).
        with pytest.raises(DuplicateKeyError):
            await store.orders.update_one({"id": "ORDB"}, {"$addToSet": {"invoiceNumbers": "invoice:2026-015"}})
        # A commercial invoice is numbered on its own.
        await store.orders.update_one({"id": "ORDB"}, {"$addToSet": {"invoiceNumbers": "commercial_invoice:2026-015"}})

        # Void, then a LEGACY record from the upgrade (no number, no lines, no total) passes the validator too.
        await svc.void_invoice("ORDA", "invoice", {"rev": 2, "reason": "Wrong prices", "by": ACTOR})
        file = {"id": "FILLEG", "kind": "invoice", "name": "ORDC.pdf", "uploadedAt": datetime.now(UTC)}
        await store.orders.update_one({"id": "ORDC"}, {"$set": {"files": [file]}})
        assert (await upgrade.invoices(store.orders))["recordsMade"] == 1
        doc = await store.orders.find_one({"id": "ORDC"})
        assert doc is not None
        assert doc["invoices"]["invoice"]["source"] == "LEGACY"
        await db.client.drop_database(db.name)

    asyncio.run(run())
