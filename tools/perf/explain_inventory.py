"""Explain every inventory-svc read on seeded data (TRD TR-DATA-5). Same idea as explain_catalog.py.

    docker run --rm --network sia-dev_default -v "$PWD/tools:/w/tools:ro" cimh/inventory-svc:dev \
        python /w/tools/perf/explain_inventory.py --mongo "mongodb://mongo:27017/?replicaSet=rs0" --units 200000

Seeds a throwaway database (`perf_inventory`, dropped afterwards) with units in every state, calls the real
InventoryService read and scan paths, records the queries they send and explains each one.
"""

from __future__ import annotations

import argparse
import asyncio
import random
import sys
from datetime import UTC, datetime, timedelta
from typing import Any

from pymongo import AsyncMongoClient
from querylog import Query, QueryLog, RecordingCollection, explain_all, report

from cimh_common.auth import Principal
from inventory_svc.service import InventoryService
from inventory_svc.store import Store

STAFF = Principal(sub="USRPERF", role="staff")
ORDER = Principal(sub="svc:order", role="service")
SHELVES = [f"SHEL{i:032x}" for i in range(60)]


class FixedPlaces:
    """Places without catalog-svc: one site, one location, 60 shelves."""

    async def list(self, **filters: Any) -> list[dict[str, Any]]:
        b = filters.get("barcode")
        if b and b.startswith("SHEL"):
            return [{"kind": "shelf", "barcode": b, "number": 1, "site": "SITE1", "location": "LOC1", "active": True}]
        if b in ("SITE1", "LOC1"):
            return [{"kind": "site" if b == "SITE1" else "location", "barcode": b, "name": b, "active": True}]
        return []

    async def put(self, place: dict[str, Any]) -> dict[str, Any]:
        return place

    async def products(self, ids: list[str]) -> list[dict[str, Any]]:
        return []


async def seed(db: Any, units: int, seed: int = 11) -> None:
    rng = random.Random(seed)  # noqa: S311 - synthetic data
    products = [f"MET{i:032x}" for i in range(max(10, units // 100))]
    t0 = datetime(2025, 1, 1, tzinfo=UTC)
    stock, storage, history = [], [], []
    for i, pid in enumerate(products):
        stock.append({"id": pid, "productName": f"Item {i:05d}", "threshold": rng.choice([0, 0, 2, 5]),
                      "active": True, "low": rng.random() < 0.1, "available": 0, "reserved": 0, "picked": 0,
                      "assigned": 0, "outbox": []})  # fmt: skip
    for i in range(units):
        pid = rng.choice(products)
        r = rng.random()
        doc: dict[str, Any] = {"barcode": f"{pid}_{i:08x}", "product": pid, "stowed": False, "picked": False,
                               "images": [], "updatedAt": t0}  # fmt: skip
        if r < 0.75:
            doc |= {"stowed": True, "shelf": rng.choice(SHELVES), "site": "SITE1", "location": "LOC1"}
            if rng.random() < 0.05:
                doc["reservedFor"] = f"ORD{rng.randint(1, 400):05d}"
        elif r < 0.9:
            doc |= {"picked": True, "orderid": f"ORD{rng.randint(1, 400):05d}" if rng.random() < 0.5 else ""}
        elif r < 0.93:
            doc["assignedTo"] = f"USR{rng.randint(1, 50):04d}"
        storage.append(doc)
        for k in range(2):
            op = "stow" if k == 0 else rng.choice(["pick", "relocate"])
            user = f"USR{rng.randint(1, 20):04d}"
            history.append(
                {"id": doc["barcode"], "operation": op, "user": user, "date": t0 + timedelta(minutes=i * 2 + k)}
            )
    for coll, docs in (("stock", stock), ("storage", storage), ("history", history)):
        for j in range(0, len(docs), 5000):
            await db[coll].insert_many(docs[j : j + 5000])


async def collect(db: Any) -> list[Query]:
    store = Store(db)
    log = QueryLog()
    for name in ("storage", "history", "stock"):
        setattr(store, name, RecordingCollection(getattr(store, name), log))
    svc = InventoryService(store, FixedPlaces())  # type: ignore[arg-type]

    async def call(label: str, coro: Any) -> Any:
        log.label = label
        return await coro

    stowed = await db.storage.find_one({"stowed": True, "reservedFor": {"$exists": False}})
    reserved = await db.storage.find_one({"reservedFor": {"$gt": ""}})
    held = await db.storage.find_one({"assignedTo": {"$gt": ""}})
    fresh = await db.storage.find_one({"stowed": False, "picked": False, "assignedTo": {"$exists": False}})
    pid = stowed["product"]

    await call("unit", svc.unit(stowed["barcode"]))
    _, nxt = await call("shelf units", svc.shelf_units(stowed["shelf"], None, 25))
    await call("shelf units p2", svc.shelf_units(stowed["shelf"], nxt, 25))
    await call("product stock", svc.product_stock(pid))
    _, nxt = await call("low stock", svc.low_stock(None, 25))
    await call("low stock p2", svc.low_stock(nxt, 25))
    _, nxt = await call("assignments", svc.assignments(None, None, 25))
    await call("assignments p2", svc.assignments(None, nxt, 25))
    await call("assignments of one", svc.assignments(held["assignedTo"], None, 25))
    _, nxt = await call("history", svc.history({}, None, 25))
    await call("history p2", svc.history({}, nxt, 25))
    await call("history unit", svc.history({"unit": stowed["barcode"]}, None, 25))
    await call("history user", svc.history({"user": "USR0003"}, None, 25))
    await call("history operation", svc.history({"operation": "relocate"}, None, 25))
    await call("availability", svc.availability([{"lineId": "L1", "productId": pid, "qty": 1}]))
    await call("reserve", svc.reserve(ORDER, "ORDPERF", [{"lineId": "L1", "productId": pid, "qty": 1}], "c"))
    await call("release", svc.release(ORDER, reserved["reservedFor"], "c"))
    await call("stow", svc.stow(STAFF, fresh["barcode"], SHELVES[0], "c"))
    await call("pick", svc.pick(STAFF, fresh["barcode"], "audit", None, "c"))
    return log.queries


async def run(mongo: str, units: int) -> int:
    client: AsyncMongoClient[dict[str, Any]] = AsyncMongoClient(mongo, tz_aware=True)
    db = client["perf_inventory"]
    try:
        await client.drop_database("perf_inventory")
        await Store(db).ensure_indexes()
        await seed(db, units)
        graded = await explain_all(db, await collect(db))
        print(f"storage documents: {units}")
        print(report(graded))
        fails = [g for g in graded if g.grade == "FAIL"]
        print(f"\n{len(graded)} queries: {len(fails)} FAIL, {sum(g.grade == 'WARN' for g in graded)} WARN")
        return 1 if fails else 0
    finally:
        await client.drop_database("perf_inventory")
        await client.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mongo", default="mongodb://mongo:27017/?replicaSet=rs0")
    ap.add_argument("--units", type=int, default=50_000)
    a = ap.parse_args()
    return asyncio.run(run(a.mongo, a.units))


if __name__ == "__main__":
    sys.exit(main())
