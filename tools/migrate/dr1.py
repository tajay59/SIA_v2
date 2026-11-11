"""DR-1 (MIGRATION_PLAN §7): load the converted export into a THROWAWAY MongoDB, run M09, verify (§6), report.

    python tools/migrate/legacy_to_v2.py db db/v2          # M01-M07 + stock
    python tools/migrate/dr1.py --legacy db --v2 db/v2 --uri mongodb://localhost:27099/?directConnection=true

`tools/migrate/dr1.sh` starts the throwaway container and runs both. The target database is wiped first, so the
script refuses any URI that is not a localhost port other than the dev stack's (27017/27018 are real databases on
this PC). Output: `<v2>/dr1/verify.json` and `verify.md`, ids and counts only (the export dir is git-ignored).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from bson import json_util
from pymongo import AsyncMongoClient, MongoClient

V2_COLLECTIONS = ["accounts", "organisations", "misc", "product", "storage", "stock", "history", "orders"]

# BSD enumerations the migrated data must stay inside.
ENUMS = {
    ("accounts", "role"): {"admin", "staff", "user"},
    ("accounts", "status"): {"PENDING_VERIFICATION", "PENDING_APPROVAL", "ACTIVE", "REJECTED", "SUSPENDED", "EXPIRED"},
    ("product", "type"): {"MET", "RAD", "EQUIP", "SUPP", "MISC", "PRO"},
    ("orders", "status"): {
        "CART",
        "SUBMITTED",
        "QUOTING",
        "QUOTED",
        "AWAITING_AGREEMENT",
        "ACCEPTED",
        "DECLINED",
        "PURCHASING",
        "APPROVED",
        "REJECTED",
        "PICKING",
        "SHIPPED",
        "DELIVERED",
        "CANCELLED",
    },
    ("orders", "type"): {"PAID", "PROBONO"},
    ("orders", "shipping.carrier"): {"FEDEX", "DHL", "HAND"},
}


def safe_uri(uri: str) -> None:
    u = urlparse(uri)
    if u.hostname not in ("localhost", "127.0.0.1") or u.port in (None, 27017, 27018):
        sys.exit(f"refusing {uri}: DR-1 wipes the target; use a throwaway localhost container (dr1.sh, port 27099)")


def load_json(path: Path) -> list[dict[str, Any]]:
    return json_util.loads(path.read_text(encoding="utf-8"))


def legacy(src: Path, name: str) -> list[dict[str, Any]]:
    return json_util.loads(Path(src, f"inventory.{name}.json").read_text(encoding="utf-8"))


def get(doc: dict[str, Any], dotted: str) -> Any:
    for part in dotted.split("."):
        if not isinstance(doc, dict):
            return None
        doc = doc.get(part)  # type: ignore[assignment]
    return doc


class Checks:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def add(self, group: str, name: str, ok: bool, detail: str = "", warn: bool = False) -> None:
        self.rows.append(
            {"group": group, "check": name, "result": "PASS" if ok else ("WARN" if warn else "FAIL"), "detail": detail}
        )

    @property
    def failed(self) -> int:
        return sum(r["result"] == "FAIL" for r in self.rows)


def load(db: Any, v2: Path) -> dict[str, int]:
    counts = {}
    for name in db.list_collection_names():
        db.drop_collection(name)
    for name in V2_COLLECTIONS:
        docs = load_json(v2 / f"{name}.json")
        if docs:
            db[name].insert_many(docs, ordered=True)
        counts[name] = len(docs)
    return counts


async def m09(uri: str, name: str) -> list[str]:
    """Indexes and the xuser view, created by the services' own code (one source of truth)."""
    from catalog_svc.store import Store as CatalogStore
    from identity_svc.store import Store as IdentityStore
    from inventory_svc.store import Store as InventoryStore
    from order_svc.store import Store as OrderStore

    client: Any = AsyncMongoClient(uri, tz_aware=True)
    db = client[name]
    done = []
    try:
        for label, store in (
            ("identity", IdentityStore(db)),
            ("catalog", CatalogStore(db)),
            ("inventory", InventoryStore(db)),
            ("order", OrderStore(db)),
        ):
            await store.ensure_indexes()
            done.append(f"{label} indexes")
        await CatalogStore(db).ensure_view()
        done.append("xuser view")
        if "products" in await db.list_collection_names():
            await db.drop_collection("products")
            done.append("dropped products")
    finally:
        await client.close()
    return done


def verify(db: Any, src: Path, report: dict[str, Any]) -> Checks:
    c = Checks()
    leg = {n: legacy(src, n) for n in ("accounts", "product", "storage", "history", "orders", "misc")}

    # Counts (§6). Accounts: duplicates merged by the converter (CLAUDE.md decision); the report says how many.
    merged = sum(1 for w in report.get("warnings", []) + report.get("review", []) if "duplicate" in w.lower())
    n_acc = db.accounts.count_documents({})
    c.add(
        "counts",
        "accounts",
        n_acc <= len(leg["accounts"]),
        f"{len(leg['accounts'])} legacy -> {n_acc} v2 "
        f"({len(leg['accounts']) - n_acc} duplicate-email accounts merged; {merged} report lines)",
    )
    for coll, src_name in (("product", "product"), ("storage", "storage"), ("history", "history")):
        a, b = len(leg[src_name]), db[coll].count_documents({})
        c.add("counts", coll, a == b, f"{a} -> {b}")
    req = db.orders.count_documents({"status": {"$ne": "CART"}})
    split = db.orders.count_documents({"history.reason": {"$regex": "split from"}, "status": {"$ne": "CART"}})
    skipped = sum(1 for w in report.get("warnings", []) if "no lines, skipped" in w)
    c.add(
        "counts",
        "orders -> requests",
        req == len(leg["orders"]) - skipped + split,
        f"{len(leg['orders'])} legacy - {skipped} empty + {split} split siblings = {req} requests; "
        f"+ {db.orders.count_documents({'status': 'CART'})} carts",
    )
    c.add(
        "counts",
        "stock (one per product)",
        db.stock.count_documents({}) == db.product.count_documents({}),
        f"{db.stock.count_documents({})} stock docs for {db.product.count_documents({})} products",
    )

    # Sums: stowed / picked units unchanged; line quantities per legacy order.
    lst = Counter(
        ("stowed" if u.get("stowed") else "") + ("+picked" if u.get("picked") else "") for u in leg["storage"]
    )
    v2st = Counter(
        ("stowed" if u.get("stowed") else "") + ("+picked" if u.get("picked") else "")
        for u in db.storage.find({}, {"stowed": 1, "picked": 1})
    )
    assigned = db.storage.count_documents({"assignedTo": {"$nin": [None]}})
    c.add(
        "sums",
        "unit states",
        sum(lst.values()) == sum(v2st.values()),
        f"legacy {dict(lst)} -> v2 {dict(v2st)}; {assigned} self-stowed units now assignedTo a person",
        warn=dict(lst) != dict(v2st),
    )
    # A mixed legacy order becomes a PAID request (same id) + a PROBONO sibling whose history says "split from <id>".
    v2_qty: Counter = Counter()
    split_re = re.compile(r"split from (ORD\w+)")
    for o in db.orders.find({"status": {"$ne": "CART"}}, {"id": 1, "history.reason": 1, "lines.qty": 1}):
        reasons = " ".join(h.get("reason") or "" for h in o.get("history", []))
        m = split_re.search(reasons)
        v2_qty[m.group(1) if m else o["id"]] += sum(int(line.get("qty", 0)) for line in o.get("lines", []))
    mismatched = []
    want_total = 0
    for o in leg["orders"]:
        items = [i for i in (o.get("cart") or []) + (o.get("ncicart") or []) if isinstance(i, dict)]
        want = sum(max(1, int(i.get("count") or 1)) for i in items)  # the converter's rule (qty >= 1)
        want_total += want
        if want and v2_qty.get(o["id"], 0) != want:
            mismatched.append(o["id"])
    c.add(
        "sums",
        "line quantities per legacy order",
        not mismatched,
        f"{len(leg['orders']) - len(mismatched)} of {len(leg['orders'])} match; "
        f"total {want_total} -> {sum(v2_qty.values())}"
        + (f"; differ: {', '.join(mismatched[:10])}" if mismatched else ""),
    )

    # References.
    pids = set(db.product.distinct("id"))
    accs = set(db.accounts.distinct("id"))
    bad_units = db.storage.count_documents({"product": {"$nin": list(pids)}})
    c.add("references", "storage.product exists", bad_units == 0, f"{bad_units} units with an unknown product")
    bad_cust = db.orders.count_documents({"customer": {"$nin": list(accs)}})
    c.add("references", "orders.customer exists", bad_cust == 0, f"{bad_cust} requests with an unknown customer")
    bad_lines = sum(
        1
        for o in db.orders.find({}, {"lines.productId": 1})
        for line in o.get("lines", [])
        if line.get("productId") not in pids
    )
    c.add("references", "orders.lines.productId exists", bad_lines == 0, f"{bad_lines} lines with an unknown product")
    no_org = db.accounts.count_documents(
        {"role": "user", "status": "ACTIVE", "isCimh": {"$ne": True}, "organisationId": None}
    )
    c.add(
        "references",
        "ACTIVE customers have an organisation",
        no_org == 0,
        f"{no_org} without one (admin assigns them before DR-2, MIGRATION_PLAN §9)",
        warn=True,
    )

    # Enumerations.
    for (coll, field), allowed in ENUMS.items():
        seen = {v for v in db[coll].distinct(field) if v is not None}
        extra = sorted(seen - allowed)
        c.add(
            "enumerations",
            f"{coll}.{field}",
            not extra,
            f"values {sorted(seen)}" + (f"; NOT allowed {extra}" if extra else ""),
        )
    c.add(
        "enumerations",
        "product sellable/probono are booleans",
        db.product.count_documents(
            {"$or": [{"sellable": {"$not": {"$type": "bool"}}}, {"probono": {"$not": {"$type": "bool"}}}]}
        )
        == 0,
    )
    c.add(
        "enumerations",
        "Pro Bono products are sellable",
        db.product.count_documents({"probono": True, "sellable": False}) == 0,
    )

    # Uniqueness (the unique indexes from M09 would also have refused duplicates on insert).
    for coll, field in (("accounts", "email"), ("storage", "barcode"), ("product", "id"), ("orders", "id")):
        dup = list(
            db[coll].aggregate([{"$group": {"_id": f"${field}", "n": {"$sum": 1}}}, {"$match": {"n": {"$gt": 1}}}])
        )
        c.add("uniqueness", f"{coll}.{field}", not dup, f"{len(dup)} duplicated values")
    carts = list(
        db.orders.aggregate(
            [
                {"$match": {"status": "CART"}},
                {"$group": {"_id": "$customer", "n": {"$sum": 1}}},
                {"$match": {"n": {"$gt": 1}}},
            ]
        )
    )
    c.add("uniqueness", "one cart per customer", not carts, f"{len(carts)} customers with more than one cart")

    # M09 state.
    c.add("m09", "xuser view exists", "xuser" in db.list_collection_names())
    c.add("m09", "products (legacy) dropped", "products" not in db.list_collection_names())
    # BSD §7 validators (applied by the services' ensure_indexes): every migrated document must satisfy them, or
    # it could not be updated once the level is strict.
    for name in V2_COLLECTIONS:
        info = next(iter(db.list_collections(filter={"name": name})), None)
        validator = (info or {}).get("options", {}).get("validator")
        if not validator:
            c.add("m09", f"validator on {name}", False, "no validator")
            continue
        bad = db[name].count_documents({"$nor": [validator]})
        c.add("m09", f"validator on {name}", bad == 0, f"{bad} of {db[name].count_documents({})} documents invalid")

    # M08 files are checked by files_to_v2.py on its own output; logins need known passwords (manual, DR-2).
    return c


def markdown(meta: dict[str, Any], checks: Checks) -> str:
    lines = [f"# DR-1 verification ({meta['at']})", "", f"Source: legacy export · target: throwaway `{meta['db']}`", ""]
    lines += [f"M09: {', '.join(meta['m09'])}", "", "| Group | Check | Result | Detail |", "|---|---|---|---|"]
    lines += [f"| {r['group']} | {r['check']} | {r['result']} | {r['detail']} |" for r in checks.rows]
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--legacy", type=Path, required=True)
    ap.add_argument("--v2", type=Path, required=True)
    ap.add_argument("--uri", required=True)
    ap.add_argument("--db", default="inventory")
    a = ap.parse_args()
    safe_uri(a.uri)

    report = json.loads((a.v2 / "report.json").read_text(encoding="utf-8"))
    client: Any = MongoClient(a.uri, tz_aware=True)
    db = client[a.db]
    started = datetime.now(UTC)
    loaded = load(db, a.v2)
    done = asyncio.run(m09(a.uri, a.db))
    checks = verify(db, a.legacy, report)
    meta = {
        "at": started.isoformat(timespec="seconds"),
        "db": a.db,
        "loaded": loaded,
        "m09": done,
        "seconds": round((datetime.now(UTC) - started).total_seconds(), 1),
    }
    out = a.v2 / "dr1"
    out.mkdir(exist_ok=True)
    (out / "verify.json").write_text(json.dumps({**meta, "checks": checks.rows}, indent=2), encoding="utf-8")
    (out / "verify.md").write_text(markdown(meta, checks), encoding="utf-8")
    summary = Counter(r["result"] for r in checks.rows)
    print(json.dumps({"loaded": loaded, "m09": done, "results": summary, "seconds": meta["seconds"]}, indent=1))
    return 1 if checks.failed else 0


if __name__ == "__main__":
    sys.exit(main())
