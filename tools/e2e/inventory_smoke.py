"""Inventory smoke test on the DEV stack (P4): places -> labels -> stow -> pick, through the real services.

    docker run --rm --network sia-dev_default -v "$PWD/tools:/w/tools:ro" cimh/inventory-svc:dev \
        python /w/tools/e2e/inventory_smoke.py

Checks the whole event path too: inventory outbox -> relay -> Kafka -> catalog-consumer -> product.inStock.
Uses a throwaway staff account (tools/perf/staff_token.py) and a product created through catalog-svc.
"""

from __future__ import annotations

import subprocess
import sys
import time
import uuid
from pathlib import Path

import httpx
from pymongo import MongoClient

INV = "http://inventory-svc:8000/api/inventory/v1"
CAT = "http://catalog-svc:8000/api/catalog/v1"
MONGO = "mongodb://mongo:27017/?replicaSet=rs0"


def check(cond: bool, label: str, r: httpx.Response | None = None) -> None:
    print(("ok   " if cond else "FAIL ") + label + ("" if cond or r is None else f"  [{r.status_code}] {r.text[:300]}"))
    if not cond:
        sys.exit(1)


def wait_for(fn: object, label: str, seconds: float = 30) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if fn():  # type: ignore[operator]
            check(True, label)
            return
        time.sleep(1)
    check(False, label)


def main() -> int:
    token = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parents[1] / "perf" / "staff_token.py")],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    h = {"Authorization": f"Bearer {token}"}
    c = httpx.Client(timeout=10)
    db = MongoClient(MONGO)["inventory"]
    run = uuid.uuid4().hex[:6]

    r = c.post(f"{CAT}/products", headers=h, json={"name": f"Smoke gauge {run}", "type": "MET",
               "department": "Meteorology", "sellable": True, "probono": False, "threshold": 1})  # fmt: skip
    check(r.status_code == 201, "staff creates a product (catalog-svc)", r)
    pid = r.json()["id"]
    wait_for(lambda: db.stock.find_one({"id": pid, "productName": {"$exists": True}}), "inventory got product.created")

    site = c.post(f"{INV}/sites", headers=h, json={"name": f"Smoke site {run}", "country": "BB"})
    check(site.status_code == 201, "site registered (stored by catalog-svc in misc)", site)
    loc = c.post(f"{INV}/sites/{site.json()['barcode']}/locations", headers=h, json={"name": "Bay 1"})
    check(loc.status_code == 201, "location created", loc)
    sh = c.post(f"{INV}/locations/{loc.json()['barcode']}/shelves", headers=h, json={"count": 2})
    check(sh.status_code == 201 and len(sh.json()["items"]) == 2, "two shelves created", sh)
    shelf = sh.json()["items"][0]["barcode"]
    check(c.get(f"{INV}/shelves/{shelf}", headers=h).json()["locationName"] == "Bay 1", "shelf scan resolves names")

    lab = c.post(f"{INV}/labels", headers=h, json={"productId": pid, "quantity": 2})
    check(lab.status_code == 201, "two unit labels", lab)
    units = lab.json()["barcodes"]
    for u in units:
        r = c.post(f"{INV}/stow", headers={**h, "Idempotency-Key": uuid.uuid4().hex}, json={"unit": u, "shelf": shelf})
        check(r.status_code == 200 and r.json()["stowed"], f"stow {u[-8:]}", r)
    wait_for(
        lambda: (db.product.find_one({"id": pid}) or {}).get("stockCount") == 2,
        "stock.changed reached catalog-svc (product.stockCount = 2, inStock)",
    )
    key = uuid.uuid4().hex
    r = c.post(f"{INV}/pick", headers={**h, "Idempotency-Key": key}, json={"unit": units[0], "reason": "smoke"})
    check(r.status_code == 200 and r.json()["picked"], "pick with a reason", r)
    again = c.post(f"{INV}/pick", headers={**h, "Idempotency-Key": key}, json={"unit": units[0], "reason": "smoke"})
    check(again.status_code == 200 and again.json() == r.json(), "replayed scan returns the first answer", again)
    st = c.get(f"{INV}/products/{pid}/stock", headers=h).json()
    check(st["available"] == 1 and st["picked"] == 1 and st["byLocation"][0]["count"] == 1, "stock counts")
    wait_for(lambda: db.stock.find_one({"id": pid, "outbox.0": {"$exists": False}}), "outbox drained by the relay")
    hist = c.get(f"{INV}/history", headers=h, params={"unit": units[0]}).json()["items"]
    check([x["operation"] for x in hist] == ["pick", "stow"], "history for the unit")
    print("inventory smoke passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
