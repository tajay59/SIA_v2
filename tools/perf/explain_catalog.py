"""Explain every catalog-svc read on seeded data (TRD TR-DATA-5; IMPLEMENTATION_PLAN P3 exit).

Run where catalog_svc is importable and Mongo is reachable, e.g. in the service image on the dev network:

    docker run --rm --network sia-dev_default -v "$PWD/tools:/w/tools:ro" cimh/catalog-svc:dev \
        python /w/tools/perf/explain_catalog.py --mongo "mongodb://mongo:27017/?replicaSet=rs0"

Calls the real CatalogService methods (public and staff) with representative filters, records the queries
they send, and explains each one. Exit 1 on any FAIL (collection scan); WARN lines are printed for review.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Any

from pymongo import AsyncMongoClient
from querylog import Query, QueryLog, RecordingCollection, explain_all, report

from catalog_svc.service import CatalogService
from catalog_svc.store import Store
from cimh_common.auth import Principal

STAFF = Principal(sub="USRPERF", role="staff")


async def collect(db: Any) -> list[Query]:
    """Call every catalogue read path once and return the queries it issued (needs seeded products)."""
    store = Store(db)
    log = QueryLog()
    store.product = RecordingCollection(store.product, log)  # type: ignore[assignment]
    store.misc = RecordingCollection(store.misc, log)  # type: ignore[assignment]
    svc = CatalogService(store)

    # Real values from the data, so equality/prefix probes hit something.
    sample = await db.product.find_one({"sellable": True, "active": True, "sn": {"$exists": True}})
    if sample is None:
        raise LookupError("no seeded products found; run seed_catalog.py first")
    pid, model, sn = sample["id"], sample["modelnumber"], sample["sn"]

    async def call(label: str, coro: Any) -> Any:
        log.label = label
        return await coro

    for who, p in (("public", None), ("staff", STAFF)):
        _, nxt = await call(f"{who} list", svc.list_products(p, {}, None, 25))
        await call(f"{who} list page 2", svc.list_products(p, {}, nxt, 25))
        await call(f"{who} list type", svc.list_products(p, {"type": "MET"}, None, 25))
        await call(f"{who} list rare type", svc.list_products(p, {"type": "PRO"}, None, 25))
        await call(f"{who} list rare type+dept", svc.list_products(p, {"type": "MISC", "department": "IT"}, None, 25))
        await call(f"{who} list type+dept", svc.list_products(p, {"type": "RAD", "department": "Radar"}, None, 25))
        await call(f"{who} list dept", svc.list_products(p, {"department": "Hydrology"}, None, 25))
        await call(f"{who} list project", svc.list_products(p, {"project": "CREWS"}, None, 25))
        await call(f"{who} list probono", svc.list_products(p, {"probono": True}, None, 25))
        await call(f"{who} list inStock", svc.list_products(p, {"inStock": True}, None, 25))
        await call(f"{who} list type+inStock=false", svc.list_products(p, {"type": "MET", "inStock": False}, None, 25))
        await call(f"{who} get", svc.get_product(p, pid))
        await call(f"{who} search make", svc.search(p, "Vaisala", {}, None, 25))
        await call(f"{who} search item", svc.search(p, "anemometer", {}, None, 25))
        await call(f"{who} search 2 words", svc.search(p, "rain gauge", {}, None, 25))
        await call(f"{who} search model", svc.search(p, model, {}, None, 25))
        await call(f"{who} search +type", svc.search(p, "cable", {"type": "SUPP"}, None, 25))
        _, nxt = await call(f"{who} search p1", svc.search(p, "sensor", {}, None, 25))
        if nxt:
            await call(f"{who} search p2", svc.search(p, "sensor", {}, nxt, 25))
    await call("staff list inactive", svc.list_products(STAFF, {"includeInactive": True}, None, 25))
    await call("staff list inactive+type", svc.list_products(STAFF, {"includeInactive": True, "type": "PRO"}, None, 25))
    await call("staff list not sellable", svc.list_products(STAFF, {"sellable": False}, None, 25))
    await call("staff search serial", svc.search(STAFF, sn[:6], {}, None, 25))
    await call("internal summaries", svc.summaries([pid, sample["id"]]))
    await call("reference", svc.reference())
    await call("internal places", svc.places({"kind": "shelf"}))
    await call("settings fees", svc.fees())
    return log.queries


async def run(mongo: str) -> int:
    db = AsyncMongoClient(mongo, tz_aware=True)["inventory"]
    try:
        queries = await collect(db)
    except LookupError as exc:
        print(exc, file=sys.stderr)
        return 2
    graded = await explain_all(db, queries)
    print(f"product documents: {await db.product.estimated_document_count()}")
    print(report(graded))
    fails = [g for g in graded if g.grade == "FAIL"]
    warns = [g for g in graded if g.grade == "WARN"]
    print(f"\n{len(graded)} queries: {len(fails)} FAIL, {len(warns)} WARN")
    return 1 if fails else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mongo", default="mongodb://mongo:27017/?replicaSet=rs0")
    return asyncio.run(run(ap.parse_args().mongo))


if __name__ == "__main__":
    sys.exit(main())
