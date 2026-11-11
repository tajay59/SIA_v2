"""Fixtures for the TEST_STRATEGY §6 mixes (browse, write, burst, soak): accounts, a staff token, products, units.

Runs inside the dev Docker network (dev stack only; refuses other Mongo hosts) and writes a JSON file that
`mix.k6.js` reads. Everything it creates is synthetic (`@example.org`, `perfmix` names).

    docker run --rm --network sia-dev_default -v "$PWD/tools:/w/tools" cimh/order-svc:dev \
        python /w/tools/perf/setup_mix.py --customers 40 --units 60 --out /w/tools/perf/results/mix-fixture.json
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from pymongo import MongoClient

ID = "http://identity-svc:8000/api/identity/v1"
CAT = "http://catalog-svc:8000/api/catalog/v1"
INV = "http://inventory-svc:8000/api/inventory/v1"
SAFE_HOSTS = {"localhost", "127.0.0.1", "mongo"}


def claim(c: httpx.Client, ref: str) -> str:
    svc = c.post(f"{ID}/internal/service-token", json={"service": "notification", "secret": "dev-notification-secret"})
    r = c.get(f"{ID}/internal/codes/{ref}", headers={"Authorization": "Bearer " + svc.json()["token"]})
    r.raise_for_status()
    return str(r.json()["code"])


def account(c: httpx.Client, db: Any, run: str, i: int, role: str, org: str | None) -> dict[str, str]:
    domain = "cimh.edu.bb" if role != "user" else "example.org"
    email, pw = f"perfmix.{run}.{i}@{domain}", f"perf mix password {run} {i}"
    body = {"firstname": "Perf", "lastname": f"Mix{i}", "email": email, "password": pw, "country": "BB",
            **({"organisationText": "Perf Mix Org"} if role == "user" else {})}  # fmt: skip
    c.post(f"{ID}/auth/register", json=body).raise_for_status()
    acc = db.accounts.find_one({"email": email})
    ref = db.temp.find_one({"accountId": acc["id"], "kind": "verify_email"})["id"]
    c.post(f"{ID}/auth/verify", json={"email": email, "code": claim(c, ref)}).raise_for_status()
    db.accounts.update_one({"email": email}, {"$set": {"status": "ACTIVE", "role": role, "organisationId": org}})
    r = c.post(f"{ID}/auth/login", json={"email": email, "password": pw, "client": "mobile"})
    r.raise_for_status()
    return {"email": email, "password": pw, "access": r.json()["accessToken"], "refresh": r.json()["refreshToken"]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mongo", default="mongodb://mongo:27017/?replicaSet=rs0")
    ap.add_argument("--customers", type=int, default=40)
    ap.add_argument("--units", type=int, default=60)
    ap.add_argument("--out", default="/w/tools/perf/results/mix-fixture.json")
    a = ap.parse_args()
    if (urlparse(a.mongo).hostname or "") not in SAFE_HOSTS:
        print("dev stack only", file=sys.stderr)
        return 2
    db = MongoClient(a.mongo)["inventory"]
    run = uuid.uuid4().hex[:6]
    c = httpx.Client(timeout=30)

    staff = account(c, db, run, 0, "staff", None)
    sh = {"Authorization": "Bearer " + staff["access"]}
    org = f"ORGPERFMIX{run}"
    customers = [account(c, db, run, i, "user", org) for i in range(1, a.customers + 1)]

    # Products customers can request (sellable, not Pro Bono, with stock so carts accept them).
    products = []
    for i in range(10):
        r = c.post(f"{CAT}/products", headers=sh, json={
            "name": f"Perf mix instrument {run} {i}", "type": "MET", "department": "Meteorology",
            "sellable": True, "probono": False, "threshold": 0, "cost": "100.00"})  # fmt: skip
        r.raise_for_status()
        products.append(r.json()["id"])

    # A site with two shelves and units on shelf A: relocate scans move units between A and B.
    site = c.post(f"{INV}/sites", headers=sh, json={"name": f"Perf mix site {run}", "country": "BB"}).json()
    loc = c.post(f"{INV}/sites/{site['barcode']}/locations", headers=sh, json={"name": "Bay"}).json()
    shelves = c.post(f"{INV}/locations/{loc['barcode']}/shelves", headers=sh, json={"count": 2}).json()["items"]
    units: list[str] = []
    per = max(1, a.units // len(products))
    for pid in products:
        units += c.post(f"{INV}/labels", headers=sh, json={"productId": pid, "quantity": per}).json()["barcodes"]
    for u in units:
        r = c.post(f"{INV}/stow", headers={**sh, "Idempotency-Key": uuid.uuid4().hex},
                   json={"unit": u, "shelf": shelves[0]["barcode"]})  # fmt: skip
        r.raise_for_status()

    fixture = {"run": run, "staff": staff, "customers": customers, "products": products, "units": units,
               "shelves": [s["barcode"] for s in shelves]}  # fmt: skip
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(fixture), encoding="utf-8")
    print(f"fixture {a.out}: {len(customers)} customers, {len(products)} products, {len(units)} units")
    return 0


if __name__ == "__main__":
    sys.exit(main())
