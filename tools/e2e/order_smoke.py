"""Order smoke test on the DEV stack (P5): a paid request from cart to delivery through the real services.

    docker run --rm --network sia-dev_default -v "$PWD/tools:/w/tools:ro" cimh/order-svc:dev \
        python /w/tools/e2e/order_smoke.py

Path: customer cart -> submit -> staff start-quoting (inventory availability) -> CIMH quote (catalog cost + fee)
-> customer agreement -> signed copy attached (as document-svc would, P6) -> accept -> order.accepted over Kafka
-> inventory reserves -> stock.reserved over Kafka -> order line RESERVED -> purchase -> picks (inventory
internal pick) -> ship -> deliver. Dev only: refuses non-local Mongo hosts.
"""

from __future__ import annotations

import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
from pymongo import MongoClient

ID = "http://identity-svc:8000/api/identity/v1"
CAT = "http://catalog-svc:8000/api/catalog/v1"
INV = "http://inventory-svc:8000/api/inventory/v1"
ORD = "http://order-svc:8000/api/orders/v1"
MONGO = "mongodb://mongo:27017/?replicaSet=rs0"


def check(cond: bool, label: str, r: httpx.Response | None = None) -> None:
    print(("ok   " if cond else "FAIL ") + label + ("" if cond or r is None else f"  [{r.status_code}] {r.text[:400]}"))
    if not cond:
        sys.exit(1)


def wait_for(fn: Any, label: str, seconds: float = 45) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if fn():
            check(True, label)
            return
        time.sleep(1)
    check(False, label)


def service_token(c: httpx.Client, name: str) -> dict[str, str]:
    r = c.post(f"{ID}/internal/service-token", json={"service": name, "secret": f"dev-{name}-secret"})
    r.raise_for_status()
    return {"Authorization": "Bearer " + r.json()["token"]}


def customer_token(c: httpx.Client, db: Any, run: str) -> dict[str, str]:
    """Register, verify (code claimed as notification-svc would), approve in the dev DB, log in."""
    email, pw = f"smoke.customer.{run}@example.org", f"smoke customer password {run}"
    body = {"firstname": "Smoke", "lastname": "Customer", "email": email, "password": pw, "country": "BB",
            "organisationText": "Smoke Met Office"}  # fmt: skip
    c.post(f"{ID}/auth/register", json=body).raise_for_status()
    acc = db.accounts.find_one({"email": email})
    ref = db.temp.find_one({"accountId": acc["id"], "kind": "verify_email"})["id"]
    code = c.get(f"{ID}/internal/codes/{ref}", headers=service_token(c, "notification")).json()["code"]
    c.post(f"{ID}/auth/verify", json={"email": email, "code": str(code)}).raise_for_status()
    db.accounts.update_one({"email": email}, {"$set": {"status": "ACTIVE", "organisationId": f"ORGSMOKE{run}"}})
    r = c.post(f"{ID}/auth/login", json={"email": email, "password": pw, "client": "mobile"})
    r.raise_for_status()
    return {"Authorization": "Bearer " + r.json()["accessToken"]}


def main() -> int:
    if "mongo:27017" not in MONGO:
        return 2
    staff_tok = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parents[1] / "perf" / "staff_token.py")],
        check=True, capture_output=True, text=True,
    ).stdout.strip()  # fmt: skip
    staff = {"Authorization": f"Bearer {staff_tok}"}
    c = httpx.Client(timeout=15)
    db = MongoClient(MONGO)["inventory"]
    run = uuid.uuid4().hex[:6]
    me = customer_token(c, db, run)

    def act(rid: str, action: str, who: dict[str, str], body: Any = None, method: str = "POST") -> httpx.Response:
        v = c.get(f"{ORD}/requests/{rid}", headers=staff).json()["version"]
        return c.request(method, f"{ORD}/requests/{rid}/{action}", headers={**who, "If-Match": str(v)}, json=body)

    # Stock: a product with a catalogue cost, two units on a shelf.
    r = c.post(f"{CAT}/products", headers=staff, json={"name": f"Smoke barometer {run}", "type": "MET",
               "department": "Meteorology", "sellable": True, "probono": False, "threshold": 0,
               "cost": "150.00"})  # fmt: skip
    check(r.status_code == 201, "staff creates a product with a cost", r)
    pid = r.json()["id"]
    wait_for(lambda: db.stock.find_one({"id": pid, "productName": {"$exists": True}}), "inventory knows the product")
    site = c.post(f"{INV}/sites", headers=staff, json={"name": f"Smoke site {run}", "country": "BB"}).json()
    loc = c.post(f"{INV}/sites/{site['barcode']}/locations", headers=staff, json={"name": "Bay 1"}).json()
    shelf = c.post(f"{INV}/locations/{loc['barcode']}/shelves", headers=staff, json={"count": 1}).json()["items"][0]
    units = c.post(f"{INV}/labels", headers=staff, json={"productId": pid, "quantity": 2}).json()["barcodes"]
    for u in units:
        r = c.post(f"{INV}/stow", headers={**staff, "Idempotency-Key": uuid.uuid4().hex},
                   json={"unit": u, "shelf": shelf["barcode"]})  # fmt: skip
        check(r.status_code == 200, f"stow {u[-8:]}", r)

    # Customer: cart -> request.
    r = c.put(f"{ORD}/cart/lines/{pid}", headers=me, json={"qty": 2})
    check(r.status_code == 200 and r.json()["lines"][0]["available"], "customer adds 2 to the cart", r)
    ship_to = {"line1": "Husbands", "city": "St James", "country": "BB", "firstname": "Smoke", "lastname": "Customer",
               "email": f"smoke.customer.{run}@example.org"}  # fmt: skip
    r = c.post(f"{ORD}/requests", headers={**me, "Idempotency-Key": run}, json={"currency": "BBD", "shipTo": ship_to})
    check(r.status_code == 201, "request submitted", r)
    rid = r.json()["requests"][0]["id"]

    # Staff: quote from CIMH stock.
    r = act(rid, "start-quoting", staff)
    check(r.status_code == 200 and r.json()["lines"][0]["cimhAvailable"] is True, "quoting: full quantity in stock", r)
    r = act(rid, "quote-draft", staff, {"supplierQuotes": [], "cimh": {"lineIds": ["L1"]}}, "PUT")
    check(r.status_code == 200, "draft: offer L1 from CIMH stock", r)
    r = act(rid, "send-quote", staff)
    check(r.status_code == 200 and r.json()["cimhQuote"]["total"] == "300.00", "CIMH quote sent (2 x 150.00)", r)

    # Customer: agreement, signed upload, acceptance.
    r = act(rid, "agreement", me, {"quoteVersion": 1, "choices": []})
    check(r.status_code == 200 and r.json()["status"] == "AWAITING_AGREEMENT", "agreement requested", r)
    fid = "FIL" + uuid.uuid4().hex
    r = c.post(f"{ORD}/internal/requests/{rid}/files", headers=service_token(c, "document"),
               json={"id": fid, "kind": "signed_agreement", "name": "signed.pdf", "mime": "application/pdf",
                     "size": 1})  # fmt: skip
    check(r.status_code == 204, "signed agreement attached (document-svc stand-in)", r)
    r = act(rid, "accept", me, {"quoteVersion": 1, "signedAgreementFileId": fid})
    check(r.status_code == 200 and r.json()["status"] == "ACCEPTED", "customer accepts with the signed copy", r)

    def reserved() -> bool:
        line = c.get(f"{ORD}/requests/{rid}", headers=staff).json()["lines"][0]
        return (line.get("reservation") or {}).get("status") == "RESERVED"

    wait_for(reserved, "order.accepted -> inventory reserved -> stock.reserved -> line RESERVED (Kafka round trip)")
    held = c.get(f"{ORD}/requests/{rid}", headers=staff).json()["lines"][0]["reservation"]["units"]
    check(sorted(held) == sorted(units), "the two stowed units are held for the request")

    # Staff: verify, pick, ship, deliver.
    r = act(rid, "purchase-orders", staff, {"agreementVerified": True, "purchaseOrders": []})
    check(r.status_code == 200 and r.json()["status"] == "PURCHASING", "signature verified -> PURCHASING", r)
    for u in held:
        r = c.post(f"{ORD}/requests/{rid}/picks", headers={**staff, "Idempotency-Key": uuid.uuid4().hex},
                   json={"lineId": "L1", "unit": u})  # fmt: skip
        check(r.status_code == 200, f"pick {u[-8:]} through order-svc -> inventory", r)
    unit = c.get(f"{INV}/units/{held[0]}", headers=staff).json()
    check(unit["picked"] and unit["orderId"] == rid, "inventory recorded the pick for the request")
    r = act(rid, "ship", staff, {"carrier": "HAND", "note": "Collected", "date": "2026-11-09"})
    check(r.status_code == 200 and r.json()["status"] == "SHIPPED", "shipped (hand delivery)", r)
    r = act(rid, "deliver", staff, {"invoiceNumber": f"SMOKE-{run}"})
    check(r.status_code == 200 and r.json()["status"] == "DELIVERED", "delivered", r)
    wait_for(
        lambda: db.orders.find_one({"id": rid, "outbox.0": {"$exists": False}}), "order outbox drained by the relay"
    )
    print("order smoke passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
