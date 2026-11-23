# ruff: noqa: E501
"""Time the SIA request desk on the DEV stack: each tab's first page, the tab counts, and what Mongo does.

Run inside the dev network (needs a staff token from staff_token.py):
  docker run --rm --network sia-dev_default -v "$(pwd -W)/tools:/w/tools:ro" cimh/order-svc:dev \
    sh -c 'python /w/tools/perf/bench_desk.py --token "$(python /w/tools/perf/staff_token.py)"'
Dev only: refuses non-local Mongo hosts. Prints numbers only, never documents.
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from urllib.parse import urlparse

import bson
import httpx
from pymongo import MongoClient

OPEN = ["SUBMITTED", "QUOTING", "QUOTED", "ACCEPTED", "PURCHASING", "APPROVED", "PICKING", "SHIPPED"]
CLOSED = ["DELIVERED", "DECLINED", "REJECTED", "CANCELLED"]
TABS = {
    "Open": (OPEN, "outstanding"),
    "New": (["SUBMITTED"], None),
    "Quoting": (["QUOTING"], None),
    "Waiting for signature": (["QUOTED"], None),
    "Signature to check": (["ACCEPTED"], None),
    "Pick & purchase": (["APPROVED", "PICKING", "PURCHASING"], None),
    "Shipped": (["SHIPPED"], None),
    "Payment due": (["DELIVERED"], "unpaid"),
    "Closed": (CLOSED, "settled"),
    "All": (OPEN + CLOSED, None),
}
COUNTS = ["SUBMITTED", "QUOTING", "QUOTED", "ACCEPTED", "APPROVED,PICKING,PURCHASING"]
SUMMARY_FIELDS = ["id", "type", "status", "customer", "customerName", "organisationId", "organisationName", "currency",
                  "lines.product.name", "quoteExpiresAt", "submittedAt", "createdAt", "updatedAt", "statusAt",
                  "payment", "files.kind", "files.deleted", "agreement.total", "total"]  # fmt: skip
UNPAID = {"type": "PAID", "status": "DELIVERED", "payment.paidAt": None}


def ms(f, n: int) -> tuple[float, float]:
    t = []
    for _ in range(n):
        s = time.perf_counter()
        f()
        t.append((time.perf_counter() - s) * 1000)
    t.sort()
    return statistics.median(t), t[max(0, int(len(t) * 0.95) - 1)]


def mongo_filter(status: list[str], payment: str | None) -> dict:
    f: dict = {"status": {"$in": status}}
    if payment == "outstanding":
        return {"$or": [f, UNPAID]}
    if payment == "settled":
        f["$nor"] = [UNPAID]
    if payment == "unpaid":
        f |= {"type": "PAID", "payment.paidAt": None}
    return f


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", required=True)
    ap.add_argument("--orders", default="http://order-svc:8000")
    ap.add_argument("--mongo", default="mongodb://mongo:27017/?replicaSet=rs0")
    ap.add_argument("-n", type=int, default=20)
    a = ap.parse_args()
    if (urlparse(a.mongo).hostname or "") not in {"localhost", "127.0.0.1", "mongo"}:
        print("dev stack only", file=sys.stderr)
        return 2
    o = MongoClient(a.mongo)["inventory"]["orders"]
    c = httpx.Client(base_url=a.orders + "/api/orders/v1", headers={"Authorization": f"Bearer {a.token}"}, timeout=30)
    print(f"requests in DB: {o.count_documents({'status': {'$ne': 'CART'}})}, runs per case: {a.n}\n")

    print("## 1. Desk page (50 rows, sort=recent) over HTTP")
    print(
        f"{'tab':24} {'median ms':>9} {'p95 ms':>7} {'KB':>6} | mongo: {'examined':>8} {'keys':>6} {'index':>30} | {'full KB':>7} {'proj KB':>7}"
    )
    for name, (st, pay) in TABS.items():
        q = {"scope": "all", "status": ",".join(st), "sort": "recent", "limit": 50} | ({"payment": pay} if pay else {})
        size = len(c.get("/requests", params=q).content)
        med, p95 = ms(lambda q=q: c.get("/requests", params=q).raise_for_status(), a.n)
        filt = mongo_filter(st, pay)
        ex = o.find(filt).sort([("statusAt", -1), ("id", -1)]).limit(51).explain()["executionStats"]
        plan = o.find(filt).sort([("statusAt", -1), ("id", -1)]).limit(51).explain()["queryPlanner"]["winningPlan"]
        idx = str(plan).split("'indexName': '")[1].split("'")[0] if "indexName" in str(plan) else "COLLSCAN"
        sort_mem = " +SORT" if "'stage': 'SORT'" in str(plan) else ""
        full = sum(len(bson.encode(d)) for d in o.find(filt).sort("statusAt", -1).limit(51))
        proj = sum(
            len(bson.encode(d)) for d in o.find(filt, {k: 1 for k in SUMMARY_FIELDS}).sort("statusAt", -1).limit(51)
        )
        print(f"{name:24} {med:9.1f} {p95:7.1f} {size / 1024:6.1f} | {ex['totalDocsExamined']:>16} {ex['totalKeysExamined']:>6} "
              f"{(idx + sort_mem)[:30]:>30} | {full / 1024:7.1f} {proj / 1024:7.1f}")  # fmt: skip

    print("\n## 2. Tab counts as today (6 list calls of up to 100 summaries)")

    def counts_now() -> None:
        for s in COUNTS:
            c.get("/requests", params={"scope": "all", "status": s, "limit": 100}).raise_for_status()
        c.get(
            "/requests", params={"scope": "all", "status": "DELIVERED", "payment": "unpaid", "limit": 100}
        ).raise_for_status()

    kb = sum(len(c.get("/requests", params={"scope": "all", "status": s, "limit": 100}).content) for s in COUNTS) / 1024
    med, p95 = ms(counts_now, a.n)
    print(f"6 calls, {kb:.0f}+ KB: median {med:.1f} ms, p95 {p95:.1f} ms (capped at 100: shows 100+)")

    print("\n## 3. Same counts done in Mongo directly (what one /requests/counts call would run)")

    def counts_db() -> None:
        for s in COUNTS:
            o.count_documents({"status": {"$in": s.split(",")}})
        o.count_documents(mongo_filter(["DELIVERED"], "unpaid"))

    med, p95 = ms(counts_db, a.n)
    print(f"exact counts: median {med:.1f} ms, p95 {p95:.1f} ms")

    print("\n## 3b. One counts call over HTTP (GET /requests/counts, exact)")
    med, p95 = ms(lambda: c.get("/requests/counts").raise_for_status(), a.n)
    print(f"median {med:.1f} ms, p95 {p95:.1f} ms")

    print("\n## 4. Name search over HTTP (indexed prefix on nameKeys + id)")
    for text in ("cas", "zzqx"):
        f = {"status": {"$ne": "CART"}, "$or": [{"id": {"$regex": f"^{text}"}}, {"nameKeys": {"$regex": f"^{text}"}}]}
        ex = o.find(f).sort("statusAt", -1).limit(51).explain()["executionStats"]
        med, p95 = ms(lambda t=text: c.get("/requests", params={"scope": "all", "status": ",".join(OPEN + CLOSED), "q": t, "sort": "recent", "limit": 50}).raise_for_status(), a.n)  # fmt: skip
        print(
            f"'{text}': median {med:.1f} ms, p95 {p95:.1f} ms; docs examined {ex['totalDocsExamined']} for {ex['nReturned']} returned"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
