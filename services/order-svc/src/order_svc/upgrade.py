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
