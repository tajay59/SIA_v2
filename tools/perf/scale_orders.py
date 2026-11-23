"""Grow the DEV orders collection to production size for bench_desk.py, then remove the copies.

  python scale_orders.py --copies 52     # adds copies with ids ORDPERF<n>_<original id>
  python scale_orders.py --clean         # deletes every ORDPERF copy
Copies keep the original's shape (no carts, no outbox), with statusAt spread over the last 3 years and quote
expiry a year out. Stop order-jobs while copies exist. Dev only: refuses non-local Mongo hosts.
"""

from __future__ import annotations

import argparse
import random
import sys
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse

from pymongo import MongoClient

PREFIX = "ORDPERF"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mongo", default="mongodb://mongo:27017/?replicaSet=rs0")
    ap.add_argument("--copies", type=int, default=0)
    ap.add_argument("--clean", action="store_true")
    a = ap.parse_args()
    if (urlparse(a.mongo).hostname or "") not in {"localhost", "127.0.0.1", "mongo"}:
        print("dev stack only", file=sys.stderr)
        return 2
    o = MongoClient(a.mongo)["inventory"]["orders"]
    if a.clean:
        print("deleted", o.delete_many({"id": {"$regex": f"^{PREFIX}"}}).deleted_count)
        return 0
    base = list(o.find({"status": {"$ne": "CART"}, "id": {"$not": {"$regex": f"^{PREFIX}"}}}, {"_id": 0, "outbox": 0}))
    rnd, now = random.Random(7), datetime.now(UTC)
    for n in range(a.copies):
        batch = []
        for d in base:
            c = dict(d)
            c["id"] = f"{PREFIX}{n}_{d['id']}"
            c.pop("cartOf", None)
            at = now - timedelta(minutes=rnd.randint(0, 3 * 365 * 24 * 60))
            c["statusAt"], c["updatedAt"] = at, at
            c["submittedAt"] = at - timedelta(days=rnd.randint(0, 60))
            if c.get("quoteExpiresAt"):
                c["quoteExpiresAt"] = now + timedelta(days=365)
            batch.append(c)
        o.insert_many(batch, ordered=False, bypass_document_validation=True)
    print("requests now", o.count_documents({"status": {"$ne": "CART"}}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
