"""Integration: inventory-svc transactions on a real MongoDB replica set (TAD §7.3; P4 exit criterion).

Two requests race for the last units: exactly one reservation wins, the other gets RESERVATION_FAILED and
holds nothing. Two devices scanning the same unit at once: one stow / one pick happens, never two.
mongomock has no transactions, so these races can only be tested here.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

pytestmark = pytest.mark.integration


class _Places:
    async def list(self, **filters: Any) -> list[dict[str, Any]]:
        b = filters.get("barcode") or ""
        if b.startswith("SHEL"):
            return [{"kind": "shelf", "barcode": b, "number": 1, "site": "SITE1", "location": "LOC1", "active": True}]
        return []

    async def put(self, place: dict[str, Any]) -> dict[str, Any]:
        return place

    async def products(self, ids: list[str]) -> list[dict[str, Any]]:
        return []


def _service(db: Any) -> Any:
    from inventory_svc.service import InventoryService
    from inventory_svc.store import Store

    return InventoryService(Store(db), _Places())


T0 = datetime(2026, 11, 1, tzinfo=UTC)


async def _setup(db: Any, pid: str, units: int, *, stowed: bool = True) -> list[str]:
    from inventory_svc.store import Store

    await Store(db).ensure_indexes()
    await db.stock.insert_one({"id": pid, "productName": "Gauge", "threshold": 0, "active": True, "outbox": []})
    codes = [f"{pid}_{i:08x}" for i in range(units)]
    await db.storage.insert_many(
        [
            # Same shape as inventory-svc writes (the BSD §7 validator requires images and timestamps).
            {
                "barcode": c,
                "product": pid,
                "stowed": stowed,
                "picked": False,
                "shelf": "SHEL1" if stowed else None,
                "images": [],
                "createdAt": T0,
                "updatedAt": T0,
            }
            for c in codes
        ]
    )
    return codes


def _run(stack: Any, body: Any) -> Any:
    from pymongo import AsyncMongoClient

    async def go() -> Any:
        client: Any = AsyncMongoClient(stack.mongo_url, tz_aware=True)
        name = f"itest_inv_{uuid.uuid4().hex[:8]}"
        try:
            return await body(client[name])
        finally:
            await client.drop_database(name)
            await client.close()

    return asyncio.run(go())


@pytest.mark.req("I9")
def test_two_reservations_for_the_last_units(stack: Any) -> None:
    from cimh_common.auth import Principal
    from cimh_common.errors import ProblemError

    order = Principal(sub="svc:order", role="service")

    async def body(db: Any) -> None:
        svc = _service(db)
        pid = "MET" + "a" * 32
        await _setup(db, pid, 3)
        for rnd in range(8):  # several rounds: the race must be lost cleanly every time
            if rnd:
                await db.storage.update_many({"product": pid}, {"$unset": {"reservedFor": "", "reservedAt": ""}})
            qty = 3 if rnd % 2 == 0 else 2  # all of the last units, or more than half of them
            lines = [{"lineId": "L1", "productId": pid, "qty": qty}]
            a, b = f"ORDA{rnd}", f"ORDB{rnd}"
            results = await asyncio.gather(
                svc.reserve(order, a, lines, "c"), svc.reserve(order, b, lines, "c"), return_exceptions=True
            )
            won = [r for r in results if not isinstance(r, BaseException)]
            lost = [r for r in results if isinstance(r, BaseException)]
            assert len(won) == 1, results
            assert len(lost) == 1
            assert isinstance(lost[0], ProblemError)
            assert lost[0].code == "RESERVATION_FAILED"
            winner = a if results[0] is won[0] else b
            loser = b if winner == a else a
            assert await db.storage.count_documents({"reservedFor": winner}) == qty
            assert await db.storage.count_documents({"reservedFor": loser}) == 0  # nothing half-reserved
            stock = await db.stock.find_one({"id": pid})
            assert (stock["reserved"], stock["available"]) == (qty, 3 - qty)  # counts committed with the units

    _run(stack, body)


@pytest.mark.req("I9")
def test_crossing_multi_line_reservations_are_all_or_nothing(stack: Any) -> None:
    """A wants P1 then P2, B wants P2 then P1, one unit each. Without a transaction each would grab one
    product and fail on the other; with it, one request gets both and the other gets nothing."""
    from cimh_common.auth import Principal

    order = Principal(sub="svc:order", role="service")

    async def body(db: Any) -> None:
        svc = _service(db)
        p1, p2 = "MET" + "c" * 32, "MET" + "d" * 32
        await _setup(db, p1, 1)
        await db.stock.insert_one({"id": p2, "productName": "Vane", "threshold": 0, "active": True, "outbox": []})
        await db.storage.insert_one(
            {"barcode": f"{p2}_00000000", "product": p2, "stowed": True, "picked": False}
            | {"images": [], "createdAt": T0, "updatedAt": T0}
        )
        for rnd in range(6):
            await db.storage.update_many({}, {"$unset": {"reservedFor": "", "reservedAt": ""}})
            l1 = {"lineId": "L1", "productId": p1, "qty": 1}
            l2 = {"lineId": "L2", "productId": p2, "qty": 1}
            a, b = f"ORDA{rnd}", f"ORDB{rnd}"
            results = await asyncio.gather(
                svc.reserve(order, a, [l1, l2], "c"), svc.reserve(order, b, [l2, l1], "c"), return_exceptions=True
            )
            assert sum(not isinstance(r, BaseException) for r in results) == 1, results
            held = {o: await db.storage.count_documents({"reservedFor": o}) for o in (a, b)}
            assert sorted(held.values()) == [0, 2], held

    _run(stack, body)


def test_same_unit_scanned_on_two_devices(stack: Any) -> None:
    from cimh_common.auth import Principal
    from cimh_common.errors import ProblemError

    a, b = Principal(sub="USRA", role="staff"), Principal(sub="USRB", role="staff")

    async def body(db: Any) -> None:
        svc = _service(db)
        pid = "MET" + "b" * 32
        units = await _setup(db, pid, 2, stowed=False)
        stows = await asyncio.gather(
            svc.stow(a, units[0], "SHEL1", "c"), svc.stow(b, units[0], "SHEL2", "c"), return_exceptions=True
        )
        assert sum(not isinstance(r, BaseException) for r in stows) == 1, stows
        assert all(r.code == "UNIT_ALREADY_STOWED" for r in stows if isinstance(r, ProblemError))
        assert await db.history.count_documents({"id": units[0], "operation": "stow"}) == 1

        picks = await asyncio.gather(
            svc.pick(a, units[0], "x", None, "c"), svc.pick(b, units[0], "y", None, "c"), return_exceptions=True
        )
        assert sum(not isinstance(r, BaseException) for r in picks) == 1, picks
        assert await db.history.count_documents({"id": units[0], "operation": "pick"}) == 1
        stock = await db.stock.find_one({"id": pid})
        assert (stock["available"], stock["picked"]) == (0, 1)
        # Every committed change carried its events, in order, on the product's stock document.
        types = [e["type"] for e in stock["outbox"]]
        assert types == ["unit.stowed", "stock.changed", "unit.picked", "stock.changed"]

    _run(stack, body)
