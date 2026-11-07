"""Seed synthetic data for dev/test (TEST_STRATEGY §8). Never uses real customer data.

    python tools/seed/seed_dev.py --mongo mongodb://localhost:27017/?replicaSet=rs0 [--products 200] [--reset]
    python tools/seed/seed_dev.py --dry-run          # print counts, write nothing

Creates, in the `inventory` database, documents shaped per BSD §5 (v2 fields):
  organisations, accounts (every role and status, incl. @cimh.edu.bb), product (all types,
  sellable/probono mixes), and one CART per member user. Deterministic for a given --seed.
Refuses to run against hosts other than localhost / docker service names unless --force.
"""

from __future__ import annotations

import argparse
import random
import sys
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

DB = "inventory"
TYPES = ["MET", "RAD", "EQUIP", "SUPP", "MISC", "PRO"]
DEPARTMENTS = ["Meteorology", "Radar", "Climate", "Hydrology", "IT"]
MAKES = ["Vaisala", "Campbell", "Davis", "Gill", "Lufft", "OTT"]
SAFE_HOSTS = {"localhost", "127.0.0.1", "mongo", "host.docker.internal"}
FIRST = ["Alex", "Sam", "Jordan", "Casey", "Riley", "Taylor", "Morgan", "Jamie"]
LAST = ["Grant", "Clarke", "Best", "Holder", "Walcott", "Small", "Brathwaite", "King"]


def now() -> datetime:
    return datetime.now(UTC)


def organisations(rng: random.Random) -> list[dict[str, Any]]:
    names = ["Barbados Met Service", "Grenada Met Office", "Jamaica Met Service", "Belize NMS", "Guyana Hydromet"]
    return [{"id": f"ORG{i:04d}", "name": n, "active": True, "createdAt": now()} for i, n in enumerate(names, 1)]


def accounts(rng: random.Random, orgs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # Placeholder hash: dev logins are created through identity-svc once it exists (P2).
    pw = "$argon2id$v=19$m=65536,t=3,p=4$ZGV2c2VlZA$ZGV2c2VlZGRldnNlZWRkZXZzZWVkZGV2c2VlZA"
    specs: list[tuple[str, str, bool]] = [
        ("admin", "ACTIVE", True),
        ("admin", "ACTIVE", True),
        ("staff", "ACTIVE", True),
        ("staff", "ACTIVE", True),
        ("staff", "SUSPENDED", True),
        ("user", "ACTIVE", True),  # @cimh.edu.bb user: cannot request
    ]
    specs += [("user", "ACTIVE", False)] * 12
    specs += [
        ("user", "PENDING_VERIFICATION", False),
        ("user", "PENDING_APPROVAL", False),
        ("user", "PENDING_APPROVAL", False),
        ("user", "REJECTED", False),
        ("user", "SUSPENDED", False),
        ("user", "EXPIRED", False),
    ]
    out = []
    for i, (role, status, cimh) in enumerate(specs, 1):
        first, last = rng.choice(FIRST), rng.choice(LAST)
        domain = "cimh.edu.bb" if cimh else "example.org"  # example.org is reserved: no real mailboxes
        org = None if cimh or status != "ACTIVE" else rng.choice(orgs)["id"]
        out.append(
            {
                "id": f"USR{i:04d}",
                "email": f"{first.lower()}.{last.lower()}.{i}@{domain}",
                "passwordHash": pw,
                "firstname": first,
                "lastname": last,
                "role": role,
                "status": status,
                "isCimh": cimh,
                "organisationId": org,
                "organisationText": None if cimh else "Some Met Office",
                "addresses": [],
                "statusHistory": [{"status": status, "at": now(), "by": "seed"}],
                "failedLogins": {"count": 0},
                "mfa": {"enabled": role == "admin"},
                "createdAt": now(),
                "updatedAt": now(),
                "version": 1,
                "outbox": [],
            }
        )
    return out


def products(rng: random.Random, n: int) -> list[dict[str, Any]]:
    out = []
    for i in range(1, n + 1):
        ptype = rng.choice(TYPES)
        probono = rng.random() < 0.05
        sellable = probono or rng.random() < 0.6
        out.append(
            {
                "id": f"P{i:06d}",
                "number": i,
                "name": f"{rng.choice(MAKES)} {ptype.title()} item {i}",
                "description": "Synthetic seed product.",
                "make": rng.choice(MAKES),
                "modelname": f"M{rng.randint(100, 999)}",
                "type": ptype,
                "department": rng.choice(DEPARTMENTS),
                "sellable": sellable,
                "probono": probono,
                "probonoMaxPerRequest": rng.choice([None, 2, 5]) if probono else None,
                "cost": f"{rng.randint(5, 25000)}.{rng.randint(0, 99):02d}",
                "threshold": rng.randint(0, 10),
                "unitquantity": 1,
                "keywords": [ptype.lower(), "seed"],
                "images": [],
                "inStock": rng.random() < 0.7,
                "active": True,
                "createdAt": now(),
                "updatedAt": now(),
                "version": 1,
                "outbox": [],
            }
        )
    return out


def carts(users: list[dict[str, Any]], prods: list[dict[str, Any]], rng: random.Random) -> list[dict[str, Any]]:
    sellable = [p for p in prods if p["sellable"]]
    out = []
    for u in users:
        if u["role"] == "user" and u["status"] == "ACTIVE" and not u["isCimh"]:
            lines = [{"productId": p["id"], "qty": rng.randint(1, 3)} for p in rng.sample(sellable, k=min(2, len(sellable)))]
            out.append(
                {
                    "id": f"CRT{u['id'][3:]}",
                    "status": "CART",
                    "requesterId": u["id"],
                    "organisationId": u["organisationId"],
                    "lines": lines,
                    "createdAt": now(),
                    "updatedAt": now(),
                    "version": 1,
                    "outbox": [],
                }
            )
    return out


def build(seed: int, n_products: int) -> dict[str, list[dict[str, Any]]]:
    rng = random.Random(seed)  # noqa: S311 - synthetic data, not security
    orgs = organisations(rng)
    users = accounts(rng, orgs)
    prods = products(rng, n_products)
    return {"organisations": orgs, "accounts": users, "product": prods, "orders": carts(users, prods, rng)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mongo", default="mongodb://localhost:27017/?directConnection=true")
    ap.add_argument("--products", type=int, default=200)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--reset", action="store_true", help="drop the seeded collections first")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="allow a non-local host (never production)")
    args = ap.parse_args(argv)

    data = build(args.seed, args.products)
    for coll, docs in data.items():
        print(f"{coll}: {len(docs)}")
    if args.dry_run:
        return 0

    host = urlparse(args.mongo).hostname or ""
    if host not in SAFE_HOSTS and not args.force:
        print(f"refusing to seed non-local host {host!r} (use --force for a disposable test DB)", file=sys.stderr)
        return 2

    from pymongo import MongoClient

    client: MongoClient[dict[str, Any]] = MongoClient(args.mongo, serverSelectionTimeoutMS=5000)
    db = client[DB]
    for coll, docs in data.items():
        if args.reset:
            db[coll].delete_many({"id": {"$in": [d["id"] for d in docs]}})
        db[coll].create_index("id", unique=True)
        if docs:
            db[coll].insert_many(docs, ordered=False)
    print("seeded", DB)
    return 0


if __name__ == "__main__":
    sys.exit(main())
