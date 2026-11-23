"""One-off data upgrades, run at start-up after the validators (idempotent; a second run changes nothing).

view_and_sign (2026-11-17, docs/plans/2026-11-17-view-and-sign.md §5): the customer no longer chooses between
CIMH stock and a supplier; staff fix the source of every line when sending the quote.
  1. lines[].choice -> lines[].source (every request).
  2. AWAITING_AGREEMENT -> QUOTED (history entry by System). The agreement the customer already has stays valid.
  3. Logged for staff (ids only; never personal data): quoted requests whose agreement was made under the old
     flow (no shipping estimate, "your choices") or that have no agreement yet. Staff revise and re-send them.
"""

from __future__ import annotations

import logging
from typing import Any

from . import domain as d
from .store import now

log = logging.getLogger("order.upgrade")
SYSTEM = {"id": "system", "name": "System", "role": "service"}
REASON = "Flow change: view and sign"


def _lines(doc: dict[str, Any]) -> list[dict[str, Any]]:
    chosen = {c.get("lineId"): c.get("choice") for c in (doc.get("agreement") or {}).get("choices") or []}
    out = []
    for ln in doc.get("lines") or []:
        source = ln.get("source") or ln.get("choice") or chosen.get(ln.get("lineId"))
        out.append({**{k: v for k, v in ln.items() if k != "choice"}, "source": source})
    return out


async def view_and_sign(orders: Any) -> dict[str, Any]:
    t = now()
    renamed = moved = 0
    filt = {"$or": [{"lines.choice": {"$exists": True}}, {"status": "AWAITING_AGREEMENT"}]}
    async for doc in orders.find(filt):
        update: dict[str, Any] = {"$set": {"lines": _lines(doc), "updatedAt": t}, "$inc": {"version": 1}}
        if doc.get("status") == "AWAITING_AGREEMENT":
            update["$set"] |= {"status": "QUOTED", "statusAt": t}
            update["$push"] = {
                "history": {"from": "AWAITING_AGREEMENT", "to": "QUOTED", "by": SYSTEM, "at": t, "reason": REASON}
            }
        res = await orders.update_one({"_id": doc["_id"], "version": doc.get("version")}, update)
        if res.modified_count:
            renamed += 1
            moved += doc.get("status") == "AWAITING_AGREEMENT"
    resend = []
    async for doc in orders.find({"type": "PAID", "status": "QUOTED"}, {"id": 1, "agreement": 1, "quoteVersion": 1}):
        ag = doc.get("agreement") or {}
        if ag.get("quoteVersion") != doc.get("quoteVersion") or "choices" in ag:
            resend.append(doc["id"])
    if renamed or moved or resend:
        log.warning(
            "view-and-sign upgrade",
            extra={"linesRenamed": renamed, "movedToQuoted": moved, "needResend": len(resend), "requestIds": resend},
        )
    return {"linesRenamed": renamed, "movedToQuoted": moved, "needResend": resend}


async def shipments(orders: Any) -> int:
    """shipments (2026-11-19, plan §5 step 4): the one `shipping` record becomes `shipments[0]` covering every line.

    Source: CIMH for Pro Bono; for paid requests the lines' source (and supplier) when they all agree, else null.
    The old field is removed so a second run finds nothing."""
    moved = 0
    async for doc in orders.find({"shipping": {"$exists": True}}):
        ship = doc.get("shipping")
        unset = {"$unset": {"shipping": ""}}
        if not isinstance(ship, dict) or not ship.get("carrier"):
            await orders.update_one({"_id": doc["_id"]}, unset)
            continue
        lines = doc.get("lines") or []
        source: str | None
        supplier: str | None
        if doc.get("type") == "PROBONO":
            source, supplier = "CIMH", None
        else:
            found = {(ln.get("source") or ln.get("choice"), ln.get("supplier")) for ln in lines}
            source, supplier = found.pop() if len(found) == 1 else (None, None)
        shipment = {
            "id": "SHP" + str(doc["id"])[-24:],
            "source": source,
            "supplier": supplier,
            "lineIds": [ln["lineId"] for ln in lines if "lineId" in ln],
            "carrier": ship["carrier"],
            "carrierName": None,
            "tracking": ship.get("tracking"),
            "trackingLink": None,
            "date": ship.get("date"),
            "cost": ship.get("cost"),
            "note": ship.get("note"),
            "by": ship.get("by") or SYSTEM,
            "at": ship.get("at") or doc.get("statusAt") or now(),
        }
        res = await orders.update_one(
            {"_id": doc["_id"], "shipping": {"$exists": True}},
            {"$set": {"shipments": [*(doc.get("shipments") or []), shipment]}, **unset},
        )
        moved += res.modified_count
    if moved:
        log.warning("shipments upgrade", extra={"requestsMoved": moved})
    return moved


async def customer_names(orders: Any, deps: Any) -> int:
    """customer names (2026-11-20): requests migrated from legacy had no `customerName`/`organisationName`, so staff
    lists showed the account id. The name comes from the request's own `customerSnapshot`; the organisation name
    is asked of identity once per customer (fail-soft: a failed lookup is retried at the next start).
    Only missing fields are written, so a second run changes nothing."""
    fixed = 0
    orgs: dict[str, str | None] = {}
    identity_down = False
    # `namesChecked` marks a request already looked at (2026-11-23): an organisation identity has no name for
    # stays empty, and without the mark every start re-read and re-asked about every such request (on the dev
    # stack: all of them; at 100k requests the walk outgrew the 256 MB worker and the restart began it again).
    filt = {
        "namesChecked": {"$ne": True},
        "$or": [
            {"customerName": {"$in": [None, ""]}},
            {"organisationName": {"$in": [None, ""]}, "organisationId": {"$nin": [None, ""]}},
        ],
    }
    fields = {"_id": 1, "customer": 1, "customerName": 1, "customerSnapshot": 1, "organisationId": 1,
              "organisationName": 1}  # fmt: skip
    async for doc in orders.find(filt, fields):
        sets: dict[str, Any] = {}
        if not doc.get("customerName"):
            snap = doc.get("customerSnapshot") or {}
            name = f"{snap.get('firstname') or ''} {snap.get('lastname') or ''}".strip() or snap.get("email")
            if name:
                sets["customerName"] = name
        if not doc.get("organisationName") and doc.get("organisationId"):
            customer = doc.get("customer")
            if customer not in orgs and not identity_down:
                try:
                    acc = await deps.account(customer) or {}
                except Exception:  # identity down: stop asking, try again next start
                    identity_down, acc = True, {}
                same_org = acc.get("organisationId") == doc.get("organisationId")  # moved since: don't guess
                orgs[customer] = acc.get("organisationName") if same_org else None
            if orgs.get(customer):
                sets["organisationName"] = orgs[customer]
        if identity_down and not sets:
            continue  # not looked at properly: try again next start
        sets["namesChecked"] = True
        sets["nameKeys"] = d.name_keys(sets.get("customerName", doc.get("customerName")),
                                       sets.get("organisationName", doc.get("organisationName")))  # fmt: skip
        res = await orders.update_one({"_id": doc["_id"]}, {"$set": sets})
        if len(sets) > 2:
            fixed += res.modified_count
    if fixed:
        log.warning("customer-names upgrade", extra={"requestsFilled": fixed})
    return fixed


async def name_keys(orders: Any) -> int:
    """name keys (2026-11-23): the staff desk searches names by an indexed prefix on lower-cased `nameKeys`.
    Fills it on requests written before; a second run changes nothing."""
    fixed = 0
    async for doc in orders.find({"nameKeys": {"$exists": False}, "status": {"$ne": "CART"}},
                                 {"_id": 1, "customerName": 1, "organisationName": 1}):  # fmt: skip
        keys = d.name_keys(doc.get("customerName"), doc.get("organisationName"))
        res = await orders.update_one({"_id": doc["_id"]}, {"$set": {"nameKeys": keys}})
        fixed += res.modified_count
    if fixed:
        log.warning("name-keys upgrade", extra={"requestsFilled": fixed})
    return fixed
