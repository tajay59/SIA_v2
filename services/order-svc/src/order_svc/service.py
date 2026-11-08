"""order-svc business rules (PRD O1-O15; BSD §5.10; API orders.openapi.yaml; TAD §7.2).

Every status change is ONE conditional update on (id, status, version): the new status, its history entry
and the outbox events commit together, and a concurrent change makes the second writer fail with 409.
Stock is never touched here: inventory-svc reserves and releases on our events and reports back with
stock.* events (consumer.py); picks go through inventory's internal pick endpoint.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from pymongo import ReturnDocument

from cimh_common.auth import Principal
from cimh_common.authz import can_see, ensure_can_act
from cimh_common.errors import ProblemError, conflict, forbidden, not_found
from cimh_common.outbox import OutboxEvent, new_event
from cimh_common.paging import clamp_limit, decode_cursor, encode_cursor

from . import domain as d
from .clients import Deps
from .store import Store, now

PUBLIC_LINE = ("lineId", "productId", "product", "qty", "cimhAvailable", "choice", "picked")


# ---------------------------------------------------------------- small helpers


def iso(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return str(value.astimezone(UTC).isoformat().replace("+00:00", "Z"))
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def aware(value: Any) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def actor(p: Principal) -> dict[str, str]:
    name = str(p.claims.get("name") or p.email or p.sub)
    return {"id": p.sub, "name": name, "role": p.role}


SYSTEM = {"id": "system", "name": "System", "role": "service"}


def invalid(field_name: str, message: str, code: str = "VALIDATION_FAILED") -> ProblemError:
    return ProblemError(422, code, message, errors=[{"field": field_name, "message": message}])


def illegal(src: str, action: str) -> ProblemError:
    return conflict("ORDER_ILLEGAL_TRANSITION", f"'{action}' is not allowed while the request is {src}")


def snapshot(product: dict[str, Any]) -> dict[str, Any]:
    images = [i for i in product.get("images") or [] if isinstance(i, dict)]
    primary = next((i for i in images if i.get("primary")), images[0] if images else None)
    return {
        "name": product.get("name") or product.get("id") or "",
        "make": product.get("make"),
        "modelname": product.get("modelname"),
        "modelnumber": product.get("modelnumber"),
        "type": product.get("type") or "MISC",
        "probono": bool(product.get("probono")),
        "image": (primary or {}).get("url"),
    }


def orderable(product: dict[str, Any] | None) -> bool:
    return bool(product and product.get("active", True) and (product.get("sellable") or product.get("probono")))


def _event(etype: str, doc: dict[str, Any], payload: dict[str, Any], p: Principal | None, cid: str) -> OutboxEvent:
    return new_event(etype, payload, correlation_id=cid or doc["id"], actor_id=p.sub if p else None)


def _move(
    etype: str, doc: dict[str, Any], src: str, dst: str, p: Principal | None, cid: str, reason: str | None = None
) -> OutboxEvent:
    payload: dict[str, Any] = {"orderId": doc["id"], "orderType": doc["type"], "customer": doc["customer"]}
    payload |= {"from": src, "to": dst, "reason": reason}
    return _event(etype, doc, payload, p, cid)


def _lines_payload(lines: list[dict[str, Any]], only_cimh: bool = False) -> list[dict[str, Any]]:
    out = []
    for ln in lines:
        if only_cimh and ln.get("choice") != d.CIMH:
            continue
        out.append({"lineId": ln["lineId"], "productId": ln["productId"], "qty": ln["qty"], "choice": ln.get("choice")})
    return out


@dataclass
class Change:
    """What one action does to a request (besides the status move, version and history)."""

    set: dict[str, Any] = field(default_factory=dict)
    events: list[OutboxEvent] = field(default_factory=list)
    reason: str | None = None
    chain: list[str] = field(default_factory=list)  # further statuses in the same step (DECLINED -> CANCELLED)


Build = Callable[[dict[str, Any], str], Awaitable[Change]]


class OrderService:
    def __init__(self, store: Store, deps: Deps, *, quote_valid_days: int = 30) -> None:
        self.store = store
        self.deps = deps
        self.quote_days = quote_valid_days

    # ================================================================== cart (O1, O12, O13)

    async def _cart(self, p: Principal) -> dict[str, Any]:
        t = now()
        doc: dict[str, Any] | None = await self.store.orders.find_one_and_update(
            {"customer": p.sub, "status": d.CART},
            {
                "$setOnInsert": {
                    "id": "CRT" + uuid.uuid4().hex,
                    "cartOf": p.sub,
                    "type": None,
                    "lines": [],
                    "version": 1,
                    "createdAt": t,
                    "updatedAt": t,
                    "history": [],
                    "outbox": [],
                }
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        if doc is None:  # upsert with ReturnDocument.AFTER always returns the cart
            raise RuntimeError("cart upsert returned nothing")
        return doc

    async def cart(self, p: Principal) -> dict[str, Any]:
        doc = await self._cart(p)
        ids = [ln["productId"] for ln in doc["lines"]]
        live: dict[str, dict[str, Any]] | None = None
        if ids:
            try:
                live = {x["id"]: x for x in await self.deps.products(ids)}
            except ProblemError:
                live = None  # show the stored snapshot; availability unknown while catalog is down
        return self.cart_view(doc, live)

    @staticmethod
    def cart_view(doc: dict[str, Any], live: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
        lines = []
        for ln in doc["lines"]:
            item: dict[str, Any] = {"productId": ln["productId"], "qty": ln["qty"], "product": ln["product"]}
            if live is not None:
                prod = live.get(ln["productId"])
                item["available"] = orderable(prod)
                if prod:
                    item["product"] = snapshot(prod)
            lines.append(item)
        return {
            "version": int(doc["version"]),
            "lines": lines,
            "hasPaidLines": any(not ln["product"]["probono"] for ln in lines),
            "hasProbonoLines": any(ln["product"]["probono"] for ln in lines),
            "updatedAt": iso(doc.get("updatedAt")),
        }

    async def _product(self, product_id: str) -> dict[str, Any]:
        found = await self.deps.products([product_id])
        prod = found[0] if found else None
        if prod is None or prod.get("deleted"):
            raise not_found("No product with this id")
        if not orderable(prod):
            raise invalid("productId", "This product can't be requested", "PRODUCT_UNAVAILABLE")
        return prod

    @staticmethod
    def _check_limit(prod: dict[str, Any], qty: int) -> None:
        cap = prod.get("probonoMaxPerRequest")
        if prod.get("probono") and isinstance(cap, int) and qty > cap:
            raise invalid("qty", f"At most {cap} per request for this Pro Bono item", "PROBONO_LIMIT_EXCEEDED")

    async def _save_cart(self, doc: dict[str, Any], lines: list[dict[str, Any]]) -> dict[str, Any]:
        res = await self.store.orders.find_one_and_update(
            {"_id": doc["_id"], "version": doc["version"]},
            {"$set": {"lines": lines, "updatedAt": now()}, "$inc": {"version": 1}},
            return_document=ReturnDocument.AFTER,
        )
        if res is None:
            raise conflict("VERSION_CONFLICT", "Your cart changed in another window; reload it")
        out: dict[str, Any] = res
        return out

    async def set_line(self, p: Principal, product_id: str, qty: int) -> dict[str, Any]:
        prod = await self._product(product_id)
        self._check_limit(prod, qty)
        doc = await self._cart(p)
        lines = [dict(ln) for ln in doc["lines"]]
        for ln in lines:
            if ln["productId"] == product_id:
                ln["qty"], ln["product"] = qty, snapshot(prod)
                break
        else:
            if len(lines) >= 200:
                raise invalid("productId", "A cart holds at most 200 products")
            lines.append({"productId": product_id, "qty": qty, "product": snapshot(prod), "addedAt": now()})
        return self.cart_view(await self._save_cart(doc, lines), {product_id: prod} | {})

    async def remove_line(self, p: Principal, product_id: str) -> dict[str, Any]:
        doc = await self._cart(p)
        lines = [ln for ln in doc["lines"] if ln["productId"] != product_id]
        if len(lines) != len(doc["lines"]):
            doc = await self._save_cart(doc, lines)
        return self.cart_view(doc)

    async def empty_cart(self, p: Principal) -> None:
        doc = await self._cart(p)
        if doc["lines"]:
            await self._save_cart(doc, [])

    # ================================================================== submission (O2, O3, O14)

    async def submit(self, p: Principal, body: dict[str, Any], cid: str) -> list[dict[str, Any]]:
        cart = await self._cart(p)
        if not cart["lines"]:
            raise invalid("cart", "Your cart is empty")
        live = {x["id"]: x for x in await self.deps.products([ln["productId"] for ln in cart["lines"]])}
        paid: list[dict[str, Any]] = []
        probono: list[dict[str, Any]] = []
        for ln in cart["lines"]:
            prod = live.get(ln["productId"])
            if not orderable(prod) or prod is None:
                msg = f"{ln['product']['name']} can no longer be requested; remove it from your cart"
                raise invalid(ln["productId"], msg, "PRODUCT_UNAVAILABLE")
            self._check_limit(prod, ln["qty"])
            (probono if prod.get("probono") else paid).append({**ln, "product": snapshot(prod)})
        if paid and not body.get("currency"):
            raise invalid("currency", "Choose BBD or USD for the items that need a quote", "CURRENCY_REQUIRED")

        account = await self.deps.account(p.sub) or {}
        first, last = account.get("firstname") or "", account.get("lastname") or ""
        customer_name = f"{first} {last}".strip() or p.email or p.sub
        t = now()
        groups = [(d.PAID, paid), (d.PROBONO, probono)]
        ids = {kind: "ORD" + uuid.uuid4().hex for kind, lines in groups if lines}
        docs = []
        for kind, lines in groups:
            if not lines:
                continue
            rid = ids[kind]
            sibling = next((v for k, v in ids.items() if k != kind), None)
            req_lines = [
                {
                    "lineId": f"L{i}",
                    "productId": ln["productId"],
                    "product": ln["product"],
                    "qty": ln["qty"],
                    "cimhAvailable": None,
                    "choice": None,
                    "reservation": None,
                    "picked": [],
                }
                for i, ln in enumerate(lines, 1)
            ]
            doc: dict[str, Any] = {
                "id": rid,
                "type": kind,
                "status": "SUBMITTED",
                "customer": p.sub,
                "customerSnapshot": {"firstname": first, "lastname": last, "email": account.get("email") or p.email},
                "customerName": customer_name,
                "organisationId": account.get("organisationId", p.org_id),
                "organisationName": account.get("organisationName"),
                "lines": req_lines,
                "currency": body.get("currency") if kind == d.PAID else None,
                "shipTo": body["shipTo"],
                "billTo": body.get("billTo") or body["shipTo"],
                "notes": body.get("notes"),
                "splitFrom": sibling,
                "version": 1,
                "createdAt": t,
                "updatedAt": t,
                "submittedAt": t,
                "statusAt": t,
                "history": [{"from": None, "to": "SUBMITTED", "by": actor(p), "at": t, "reason": None}],
                "files": [],
                "quotes": [],
            }
            payload = {"orderId": rid, "type": kind, "customer": p.sub, "organisationId": doc["organisationId"]}
            payload |= {"currency": doc["currency"], "lines": _lines_payload(req_lines), "splitFrom": sibling}
            doc["outbox"] = [_event("order.submitted", doc, payload, p, cid).model_dump(mode="python")]
            docs.append(doc)

        async def tx(s: Any) -> None:
            res = await self.store.orders.update_one(
                {"_id": cart["_id"], "version": cart["version"]},
                {"$set": {"lines": [], "updatedAt": t}, "$inc": {"version": 1}},
                session=s,
            )
            if res.matched_count != 1:
                raise conflict("VERSION_CONFLICT", "Your cart changed while submitting; review it and try again")
            await self.store.orders.insert_many(docs, session=s)

        await self.store.transaction(tx)
        return [self.view(doc, p) for doc in docs]

    # ================================================================== reading (O4)

    async def get(self, p: Principal, rid: str) -> dict[str, Any]:
        return self.view(await self._visible(p, rid), p)

    async def _load(self, rid: str) -> dict[str, Any]:
        doc: dict[str, Any] | None = await self.store.orders.find_one({"id": rid, "status": {"$ne": d.CART}})
        if doc is None:
            raise not_found("No request with this id")
        return doc

    async def _visible(self, p: Principal, rid: str) -> dict[str, Any]:
        doc = await self._load(rid)
        if not can_see(p, owner_id=doc["customer"], org_id=doc.get("organisationId"), same_org=True):
            raise not_found("No request with this id")
        return doc

    async def list_requests(
        self, p: Principal, q: dict[str, Any], cursor: str | None, limit: int | None
    ) -> tuple[list[dict[str, Any]], str | None]:
        n = clamp_limit(limit)
        scope = q.get("scope") or "mine"
        filt: dict[str, Any] = {"status": {"$in": q["status"]} if q.get("status") else {"$ne": d.CART}}
        if p.is_staff:
            if q.get("organisationId"):
                filt["organisationId"] = q["organisationId"]
        else:
            if scope == "all":
                raise forbidden("Only staff can list all requests")
            if q.get("organisationId"):
                raise forbidden("Only staff can filter by organisation")
            if scope == "organisation":
                filt["organisationId"] = p.org_id or "\0none"
            else:
                filt["customer"] = p.sub
        if q.get("customer"):
            filt["customer"] = q["customer"] if p.is_staff or scope == "organisation" else p.sub
            if not p.is_staff and scope != "organisation" and q["customer"] != p.sub:
                filt["customer"] = "\0none"
        if q.get("type"):
            filt["type"] = q["type"]
        if q.get("year"):
            y = int(q["year"])
            filt["submittedAt"] = {"$gte": datetime(y, 1, 1, tzinfo=UTC), "$lt": datetime(y + 1, 1, 1, tzinfo=UTC)}
        if q.get("q") and p.is_staff:
            rx = {"$regex": "^" + re.escape(q["q"]), "$options": "i"}
            filt["$or"] = [{"id": rx}, {"customerName": rx}, {"organisationName": rx}]
        sort = q.get("sort") or "newest"
        field_, desc = {"newest": ("submittedAt", True), "oldest": ("submittedAt", False)}.get(
            sort, ("statusAt", False)
        )
        if cursor:
            value, cid_ = decode_cursor(cursor)
            if isinstance(value, str) and value and field_ != "id":
                value = datetime.fromisoformat(value)
            op = "$lt" if desc else "$gt"
            after = {"$or": [{field_: {op: value}}, {field_: value, "id": {op: cid_}}]}
            filt = {"$and": [filt, after]}
        direction = -1 if desc else 1
        docs = await self.store.orders.find(filt).sort([(field_, direction), ("id", direction)]).limit(n + 1).to_list()
        nxt = None
        if len(docs) > n:
            docs = docs[:n]
            last = docs[-1]
            nxt = encode_cursor(aware(last.get(field_)), last["id"])
        return [self.summary(x) for x in docs], nxt

    # ================================================================== views

    @staticmethod
    def summary(doc: dict[str, Any]) -> dict[str, Any]:
        since = aware(doc.get("statusAt")) or aware(doc.get("updatedAt")) or now()
        return {
            "id": doc["id"],
            "type": doc["type"],
            "status": doc["status"],
            "customer": doc["customer"],
            "customerName": doc.get("customerName") or doc["customer"],
            "organisationId": doc.get("organisationId"),
            "organisationName": doc.get("organisationName"),
            "currency": doc.get("currency"),
            "lineCount": len(doc.get("lines") or []),
            "quoteExpiresAt": iso(doc.get("quoteExpiresAt")) if doc["status"] in d.QUOTE_LIVE else None,
            "submittedAt": iso(doc.get("submittedAt")) or iso(doc.get("createdAt")) or "",
            "updatedAt": iso(doc.get("updatedAt")),
            "waitingDays": max(0, (now() - since).days),
            "version": int(doc.get("version") or 1),
        }

    def view(self, doc: dict[str, Any], p: Principal) -> dict[str, Any]:
        staff = p.is_staff
        out = self.summary(doc)
        lines = []
        for ln in doc.get("lines") or []:
            item = {k: ln.get(k) for k in PUBLIC_LINE}
            item["picked"] = [
                {"barcode": x.get("barcode"), "pickedBy": x.get("pickedby"), "pickedDate": iso(x.get("pickeddate"))}
                for x in ln.get("picked") or []
            ]
            res = ln.get("reservation")
            item["reservation"] = (
                {"status": res.get("status", "NONE"), **({"units": res.get("units", [])} if staff else {})}
                if isinstance(res, dict)
                else None
            )
            lines.append(item)
        quotes = []
        for qt in doc.get("quotes") or []:
            item = {
                "id": qt["id"],
                "version": qt["version"],
                "lines": [
                    {"lineId": x["lineId"], "unitPrice": d.money_str(x["unitPrice"]), "total": d.money_str(x["total"])}
                    for x in qt["lines"]
                ],
                "total": d.money_str(qt["total"]),
                "fileIds": list(qt.get("fileIds") or []),
                "expiresAt": iso(qt["expiresAt"]),
                "sentAt": iso(qt.get("sentAt")),
            }
            if staff:
                item["supplier"] = qt.get("supplier")
            quotes.append(item)
        cq = doc.get("cimhQuote")
        cimh = None
        if cq:
            cimh = {
                "version": cq["version"],
                "exchangeRate": str(cq["exchangeRate"]) if cq.get("exchangeRate") is not None else None,
                "lines": [],
                "total": d.money_str(cq["total"]),
                "fileId": cq.get("fileId"),
            }
            for x in cq["lines"]:
                row = {
                    "lineId": x["lineId"],
                    "unitPrice": d.money_str(x["unitPrice"]),
                    "total": d.money_str(x["total"]),
                }
                if staff:
                    row["unitCostBBD"] = d.money_str(x.get("unitCostBBD"))
                cimh["lines"].append(row)
        ag = doc.get("agreement")
        agreement = None
        if ag:
            agreement = {
                "quoteVersion": ag["quoteVersion"],
                "choices": ag["choices"],
                "total": d.money_str(ag["total"]),
                "fileId": ag.get("fileId"),
                "signedFileId": ag.get("signedFileId"),
                "verified": self._who(ag.get("verified")),
                "rejections": [{"reason": r.get("reason"), "at": iso(r.get("at"))} for r in ag.get("rejections") or []],
            }
        acc = doc.get("acceptance")
        ship = doc.get("shipping")
        out |= {
            "lines": lines,
            "shipTo": doc.get("shipTo"),
            "billTo": doc.get("billTo"),
            "notes": doc.get("notes"),
            "splitFrom": doc.get("splitFrom"),
            "quotes": quotes,
            "cimhQuote": cimh,
            "adminFee": d.money_str(doc.get("adminFee")),
            "acceptance": {
                "quoteVersion": acc["quoteVersion"],
                "choices": acc["choices"],
                "signedAgreementFileId": acc["agreementFileId"],
                "by": acc["by"],
                "at": iso(acc["at"]),
            }
            if acc
            else None,
            "agreement": agreement,
            "decline": self._who(doc.get("decline")),
            "approval": self._who(doc.get("approval")),
            "rejection": self._who(doc.get("rejection")),
            "shipping": {
                "carrier": ship["carrier"],
                "tracking": ship.get("tracking"),
                "trackingUrl": d.tracking_url(ship["carrier"], ship.get("tracking")),
                "note": ship.get("note"),
                "date": iso(ship.get("date")),
            }
            if ship
            else None,
            "invoice": {"number": doc["invoice"].get("number"), "date": iso(doc["invoice"].get("date"))}
            if doc.get("invoice")
            else None,
            "files": [self._file(f) for f in doc.get("files") or [] if not f.get("deleted")],
            "cancellation": self._who(doc.get("cancellation")),
            "history": [
                {"from": h.get("from"), "to": h["to"], "by": h["by"], "at": iso(h["at"]), "reason": h.get("reason")}
                for h in doc.get("history") or []
            ],
            "allowedActions": self.allowed_actions(doc, p),
        }
        if staff:
            out["purchaseOrders"] = [
                {**po, "placedAt": iso(po.get("placedAt"))} for po in doc.get("purchaseOrders") or []
            ]
            draft = doc.get("quoteDraft")
            if draft:
                out["quoteDraft"] = {
                    "supplierQuotes": [
                        {
                            "supplier": s["supplier"],
                            "fileIds": s.get("fileIds", []),
                            "lines": [
                                {"lineId": x["lineId"], "unitPrice": d.money_str(x["unitPrice"])} for x in s["lines"]
                            ],
                        }
                        for s in draft.get("supplierQuotes", [])
                    ],
                    "cimh": draft.get("cimh"),
                    "savedAt": iso(draft.get("savedAt")),
                }
        return out

    @staticmethod
    def _who(v: Any) -> dict[str, Any] | None:
        if not isinstance(v, dict):
            return None
        return {k: (iso(x) if k == "at" else x) for k, x in v.items()}

    @staticmethod
    def _file(f: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": f["id"],
            "kind": f["kind"],
            "name": f.get("name") or f["id"],
            "mime": f.get("mime") or "application/octet-stream",
            "size": int(f.get("size") or 0),
            "uploadedAt": iso(f.get("uploadedAt")),
            "url": f"/api/documents/v1/files/{f['id']}",
        }

    def allowed_actions(self, doc: dict[str, Any], p: Principal) -> list[str]:
        t, st = doc["type"], doc["status"]
        requester = p.sub == doc["customer"] or p.is_admin
        out: list[str] = []
        if requester:
            if t == d.PAID and st in d.QUOTE_LIVE:
                out.append("agreement")
            if st == "AWAITING_AGREEMENT":
                out.append("accept")
            if st == "QUOTED":
                out.append("decline")
        who = d.who_may(t, st, "CANCELLED")
        if who and who != "system" and (p.is_staff or (who == "any" and requester)):
            out.append("cancel")
        if p.is_staff:
            if t == d.PAID:
                out += {
                    "SUBMITTED": ["start-quoting"],
                    "QUOTING": ["quote-draft", "send-quote"],
                    "QUOTED": ["quote-draft", "send-quote"],
                    "ACCEPTED": ["reject-agreement", "purchase-orders"],
                    "PURCHASING": ["ship"],
                    "SHIPPED": ["deliver"],
                }.get(st, [])
                if st == "PURCHASING" and self._pickable(doc):
                    out.insert(len(out) - 1, "pick")
            else:
                out += {
                    "SUBMITTED": ["approve", "reject"],
                    "APPROVED": ["pick"],
                    "PICKING": ["pick", "ship"],
                    "SHIPPED": ["deliver"],
                }.get(st, [])
        return out

    @staticmethod
    def _pickable(doc: dict[str, Any]) -> list[dict[str, Any]]:
        return [ln for ln in doc.get("lines") or [] if doc["type"] == d.PROBONO or ln.get("choice") == d.CIMH]

    # ================================================================== transitions

    async def _act(
        self, p: Principal, rid: str, version: int, action: str, build: Build, *, who_check: bool = True
    ) -> dict[str, Any]:
        doc = await self._visible(p, rid)
        if action in ("agreement", "accept", "decline") or (action == "cancel" and not p.is_staff):
            ensure_can_act(p, owner_id=doc["customer"], org_id=doc.get("organisationId"))
        if int(doc.get("version") or 1) != version:
            raise conflict("VERSION_CONFLICT", "The request changed meanwhile; reload it")
        src = doc["status"]
        moves = d.sources(doc["type"], action)
        if action == "agreement" and doc["type"] == d.PAID:
            moves["AWAITING_AGREEMENT"] = "AWAITING_AGREEMENT"  # new choices replace the agreement (contract)
        if src not in moves:
            raise illegal(src, action)
        dst = moves[src]
        who = d.who_may(doc["type"], src, dst) or ("requester" if action == "agreement" else "staff")
        if who_check and who == "staff" and not p.is_staff:
            raise forbidden("Only staff can do this now")
        change = await build(doc, dst)
        t = now()
        steps = [dst, *change.chain]
        hist, prev = [], src
        for s in steps:
            if s != prev or action == "send-quote":
                hist.append({"from": prev, "to": s, "by": actor(p), "at": t, "reason": change.reason})
            prev = s
        final = steps[-1]
        update: dict[str, Any] = {
            "$set": {"status": final, "updatedAt": t, **({"statusAt": t} if final != src else {}), **change.set},
            "$inc": {"version": 1},
        }
        push: dict[str, Any] = {}
        if hist:
            push["history"] = {"$each": hist}
        if change.events:
            push["outbox"] = {"$each": [e.model_dump(mode="python") for e in change.events]}
        if push:
            update["$push"] = push
        res = await self.store.orders.find_one_and_update(
            {"id": rid, "status": src, "version": version}, update, return_document=ReturnDocument.AFTER
        )
        if res is None:
            raise conflict("VERSION_CONFLICT", "The request changed meanwhile; reload it")
        return self.view(res, p)

    # ---------------------------------------------------------------- paid: quoting (O5, O5a, O7, O15)

    async def start_quoting(self, p: Principal, rid: str, version: int, cid: str) -> dict[str, Any]:
        async def build(doc: dict[str, Any], dst: str) -> Change:
            ask = [{"lineId": ln["lineId"], "productId": ln["productId"], "qty": ln["qty"]} for ln in doc["lines"]]
            avail = {x["lineId"]: bool(x.get("fullQuantity")) for x in await self.deps.availability(ask)}
            lines = [{**ln, "cimhAvailable": avail.get(ln["lineId"], False)} for ln in doc["lines"]]
            return Change(
                set={"lines": lines}, events=[_move("order.quoting_started", doc, doc["status"], dst, p, cid)]
            )

        return await self._act(p, rid, version, "start-quoting", build)

    async def save_draft(self, p: Principal, rid: str, version: int, body: dict[str, Any]) -> dict[str, Any]:
        doc = await self._load(rid)
        if int(doc.get("version") or 1) != version:
            raise conflict("VERSION_CONFLICT", "The request changed meanwhile; reload it")
        if doc["type"] != d.PAID or doc["status"] not in ("QUOTING", "QUOTED"):
            raise illegal(doc["status"], "quote-draft")
        by_id = {ln["lineId"]: ln for ln in doc["lines"]}
        seen: set[str] = set()
        quotes = []
        for i, sq in enumerate(body.get("supplierQuotes") or []):
            rows = []
            for x in sq["lines"]:
                if x["lineId"] not in by_id:
                    raise invalid(f"supplierQuotes[{i}]", f"Unknown line {x['lineId']}")
                if x["lineId"] in seen:
                    raise invalid(f"supplierQuotes[{i}]", f"Line {x['lineId']} has a price from two suppliers")
                seen.add(x["lineId"])
                rows.append({"lineId": x["lineId"], "unitPrice": d.to_db(d.money(x["unitPrice"]))})
            quotes.append({"supplier": sq["supplier"], "lines": rows, "fileIds": list(sq.get("fileIds") or [])})
        cimh = body.get("cimh")
        if cimh:
            for lid in cimh.get("lineIds") or []:
                if not by_id.get(lid, {}).get("cimhAvailable"):
                    raise invalid("cimh.lineIds", f"Line {lid} is not fully in CIMH stock")
            cimh = {"lineIds": list(dict.fromkeys(cimh.get("lineIds") or [])), "exchangeRate": cimh.get("exchangeRate")}
        draft = {"supplierQuotes": quotes, "cimh": cimh, "savedBy": actor(p), "savedAt": now()}
        res = await self.store.orders.find_one_and_update(
            {"id": rid, "version": version, "status": doc["status"]},
            {"$set": {"quoteDraft": draft, "updatedAt": now()}, "$inc": {"version": 1}},
            return_document=ReturnDocument.AFTER,
        )
        if res is None:
            raise conflict("VERSION_CONFLICT", "The request changed meanwhile; reload it")
        return self.view(res, p)

    async def send_quote(self, p: Principal, rid: str, version: int, cid: str) -> dict[str, Any]:
        async def build(doc: dict[str, Any], dst: str) -> Change:
            draft = doc.get("quoteDraft") or {}
            cur = doc["currency"] or "BBD"
            supplier_lines = {x["lineId"] for sq in draft.get("supplierQuotes") or [] for x in sq["lines"]}
            cimh_cfg = draft.get("cimh") or {}
            cimh_ids = [x for x in cimh_cfg.get("lineIds") or [] if x in {ln["lineId"] for ln in doc["lines"]}]
            missing = [ln["lineId"] for ln in doc["lines"] if ln["lineId"] not in supplier_lines | set(cimh_ids)]
            if missing:
                raise invalid("lines", f"No price yet for {', '.join(missing)}", "QUOTE_INCOMPLETE")
            fee_bbd = await self.deps.admin_fee()
            raw_rate = cimh_cfg.get("exchangeRate")
            ex = d.rate(raw_rate) if raw_rate else None
            if cur == "USD" and ex is None and (cimh_ids or fee_bbd > 0):
                raise invalid("cimh.exchangeRate", "Enter the BBD-per-USD exchange rate", "EXCHANGE_RATE_REQUIRED")
            t = now()
            qv = int(doc.get("quoteVersion") or 0) + 1
            expires = t + timedelta(days=self.quote_days)
            quotes = []
            for sq in draft.get("supplierQuotes") or []:
                rows, total = [], Decimal("0")
                qty = {ln["lineId"]: ln["qty"] for ln in doc["lines"]}
                for x in sq["lines"]:
                    unit = d.money(x["unitPrice"])
                    line_total = d.money(unit * qty[x["lineId"]])
                    total += line_total
                    rows.append({"lineId": x["lineId"], "unitPrice": d.to_db(unit), "total": d.to_db(line_total)})
                quotes.append(
                    {
                        "id": "QTE" + uuid.uuid4().hex,
                        "version": qv,
                        "supplier": sq["supplier"],
                        "lines": rows,
                        "total": d.to_db(total),
                        "fileIds": sq.get("fileIds", []),
                        "expiresAt": expires,
                        "sentAt": t,
                        "sentBy": actor(p),
                    }
                )
            cimh_quote = None
            if cimh_ids:
                prods = {x["id"]: x for x in await self.deps.products([ln["productId"] for ln in doc["lines"]])}
                rows, total = [], Decimal("0")
                for ln in doc["lines"]:
                    if ln["lineId"] not in cimh_ids:
                        continue
                    cost = (prods.get(ln["productId"]) or {}).get("cost")
                    if cost in (None, ""):
                        raise invalid(
                            ln["lineId"], f"{ln['product']['name']} has no catalogue cost", "QUOTE_INCOMPLETE"
                        )
                    unit = d.convert_bbd(d.money(cost), cur, ex)
                    line_total = d.money(unit * ln["qty"])
                    total += line_total
                    rows.append(
                        {
                            "lineId": ln["lineId"],
                            "unitCostBBD": d.to_db(d.money(cost)),
                            "unitPrice": d.to_db(unit),
                            "total": d.to_db(line_total),
                        }
                    )
                cimh_quote = {
                    "version": qv,
                    "exchangeRate": str(ex) if ex is not None else None,
                    "lines": rows,
                    "total": d.to_db(total),
                    "fileId": None,
                }
            fee = d.convert_bbd(fee_bbd, cur, ex) if fee_bbd > 0 else Decimal("0")
            src = doc["status"]
            if src == "QUOTING":
                payload = {
                    "orderId": doc["id"],
                    "customer": doc["customer"],
                    "quoteVersion": qv,
                    "expiresAt": iso(expires),
                    "currency": cur,
                    "cimhLineIds": cimh_ids,
                }
                event = _event("order.quoted", doc, payload, p, cid)
            else:
                event = _move("order.quote_revised", doc, src, dst, p, cid, f"quote version {qv}")
            change = Change(
                set={
                    "quoteVersion": qv,
                    "quoteExpiresAt": expires,
                    "cimhQuote": cimh_quote,
                    "adminFee": d.to_db(fee),
                    "quotes": [*doc.get("quotes", []), *quotes],
                },
                events=[event],
                reason=None if src == "QUOTING" else f"quote version {qv}",
            )
            return change

        return await self._act(p, rid, version, "send-quote", build)

    # ---------------------------------------------------------------- paid: agreement and acceptance (O6, O6a)

    def _quote_live(self, doc: dict[str, Any], quote_version: int) -> None:
        if quote_version != int(doc.get("quoteVersion") or 0):
            raise conflict("QUOTE_OUTDATED", "The quote was revised; review the latest version")
        exp = aware(doc.get("quoteExpiresAt"))
        if exp is not None and exp < now():
            raise conflict("QUOTE_EXPIRED", "This quote has expired")

    @staticmethod
    def _offers(doc: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        qv = int(doc.get("quoteVersion") or 0)
        supplier = {x["lineId"]: x for q in doc.get("quotes") or [] if q["version"] == qv for x in q["lines"]}
        cq = doc.get("cimhQuote") or {}
        cimh = {x["lineId"]: x for x in cq.get("lines") or []} if cq.get("version") == qv else {}
        return supplier, cimh

    async def agreement(self, p: Principal, rid: str, version: int, body: dict[str, Any], cid: str) -> dict[str, Any]:
        async def build(doc: dict[str, Any], dst: str) -> Change:
            self._quote_live(doc, body["quoteVersion"])
            supplier, cimh = self._offers(doc)
            given = {c["lineId"]: c["choice"] for c in body["choices"]}
            known = {ln["lineId"] for ln in doc["lines"]}
            for lid in given:
                if lid not in known:
                    raise invalid("choices", f"Unknown line {lid}")
            choices, total = [], d.money(doc.get("adminFee") or 0)
            for ln in doc["lines"]:
                opts = d.line_options(ln["lineId"], supplier, cimh)
                choice = given.get(ln["lineId"])
                if choice is None:
                    if len(opts) != 1:
                        raise invalid(
                            ln["lineId"],
                            f"Choose CIMH stock or supplier for {ln['product']['name']}",
                            "CHOICE_REQUIRED",
                        )
                    choice = opts[0]
                elif choice not in opts:
                    raise invalid(ln["lineId"], f"{choice} is not offered for {ln['product']['name']}")
                total += d.money((cimh if choice == d.CIMH else supplier)[ln["lineId"]]["total"])
                choices.append({"lineId": ln["lineId"], "choice": choice})
            old = doc.get("agreement") or {}
            agreement = {
                "quoteVersion": body["quoteVersion"],
                "choices": choices,
                "total": d.to_db(total),
                "fileId": None,
                "signedFileId": None,
                "verified": None,
                "rejections": old.get("rejections", []),
                "requestedAt": now(),
            }
            chosen = {c["lineId"]: c["choice"] for c in choices}
            lines = [{**ln, "choice": chosen[ln["lineId"]]} for ln in doc["lines"]]
            payload = {
                "orderId": doc["id"],
                "customer": doc["customer"],
                "quoteVersion": body["quoteVersion"],
                "lines": _lines_payload(lines),
                "total": d.money_str(total),
                "currency": doc["currency"],
            }
            return Change(
                set={"agreement": agreement}, events=[_event("order.agreement_requested", doc, payload, p, cid)]
            )

        return await self._act(p, rid, version, "agreement", build)

    async def accept(
        self, p: Principal, rid: str, version: int, body: dict[str, Any], ip: str | None, cid: str
    ) -> dict[str, Any]:
        async def build(doc: dict[str, Any], dst: str) -> Change:
            ag = doc.get("agreement") or {}
            if body["quoteVersion"] != ag.get("quoteVersion"):
                raise conflict("QUOTE_OUTDATED", "Accept the agreement for the latest quote")
            self._quote_live(doc, body["quoteVersion"])
            fid = body["signedAgreementFileId"]
            ok = any(
                f["id"] == fid and f["kind"] == "signed_agreement" and not f.get("deleted")
                for f in doc.get("files") or []
            )
            if not ok:
                raise invalid("signedAgreementFileId", "Upload the signed agreement first", "AGREEMENT_REQUIRED")
            t = now()
            chosen = {c["lineId"]: c["choice"] for c in ag["choices"]}
            lines = []
            for ln in doc["lines"]:
                ch = chosen.get(ln["lineId"])
                res = {"status": "NONE", "units": []} if ch == d.CIMH else None
                lines.append({**ln, "choice": ch, "reservation": res})
            acceptance = {
                "quoteVersion": body["quoteVersion"],
                "agreementFileId": fid,
                "choices": ag["choices"],
                "by": actor(p),
                "at": t,
                "ip": ip,
            }
            payload = {
                "orderId": doc["id"],
                "customer": doc["customer"],
                "quoteVersion": body["quoteVersion"],
                "lines": _lines_payload(lines),
            }
            return Change(
                set={"lines": lines, "acceptance": acceptance, "agreement.signedFileId": fid},
                events=[_event("order.accepted", doc, payload, p, cid)],
            )

        return await self._act(p, rid, version, "accept", build)

    async def reject_agreement(self, p: Principal, rid: str, version: int, reason: str, cid: str) -> dict[str, Any]:
        async def build(doc: dict[str, Any], dst: str) -> Change:
            ag = dict(doc.get("agreement") or {})
            ag["rejections"] = [*ag.get("rejections", []), {"by": actor(p), "at": now(), "reason": reason}]
            ag |= {"signedFileId": None, "verified": None}
            lines = [{**ln, "reservation": None} for ln in doc["lines"]]
            return Change(
                set={"agreement": ag, "acceptance": None, "lines": lines},
                events=[_move("order.agreement_rejected", doc, doc["status"], dst, p, cid, reason)],
                reason=reason,
            )

        return await self._act(p, rid, version, "reject-agreement", build)

    async def decline(self, p: Principal, rid: str, version: int, reason: str, cid: str) -> dict[str, Any]:
        async def build(doc: dict[str, Any], dst: str) -> Change:
            who = {"by": actor(p), "at": now(), "reason": reason}
            return Change(
                set={"decline": who, "cancellation": {**who, "auto": False}},
                events=[_move("order.declined", doc, doc["status"], dst, p, cid, reason)],
                reason=reason,
                chain=["CANCELLED"],
            )

        return await self._act(p, rid, version, "decline", build)

    async def cancel(self, p: Principal, rid: str, version: int, reason: str, cid: str) -> dict[str, Any]:
        async def build(doc: dict[str, Any], dst: str) -> Change:
            payload = {"orderId": doc["id"], "customer": doc["customer"], "reason": reason, "auto": False}
            return Change(
                set={"cancellation": {"by": actor(p), "at": now(), "reason": reason, "auto": False}},
                events=[_event("order.cancelled", doc, payload, p, cid)],
                reason=reason,
            )

        return await self._act(p, rid, version, "cancel", build)

    async def purchase_orders(
        self, p: Principal, rid: str, version: int, body: dict[str, Any], cid: str
    ) -> dict[str, Any]:
        async def build(doc: dict[str, Any], dst: str) -> Change:
            if body.get("agreementVerified") is not True:
                raise invalid("agreementVerified", "Verify the signed agreement first", "AGREEMENT_NOT_VERIFIED")
            supplier_lines = {ln["lineId"] for ln in doc["lines"] if ln.get("choice") == d.SUPPLIER}
            covered: set[str] = set()
            t = now()
            pos = []
            for i, po in enumerate(body["purchaseOrders"]):
                bad = [x for x in po["lineIds"] if x not in supplier_lines]
                if bad:
                    raise invalid(f"purchaseOrders[{i}]", f"Not supplier lines: {', '.join(bad)}")
                covered |= set(po["lineIds"])
                pos.append({**po, "placedAt": t, "placedBy": actor(p)})
            if supplier_lines - covered:
                missing = ", ".join(sorted(supplier_lines - covered))
                raise invalid("purchaseOrders", f"No purchase order for {missing}")
            return Change(
                set={"purchaseOrders": pos, "agreement.verified": {"by": actor(p), "at": t}},
                events=[_move("order.purchasing", doc, doc["status"], dst, p, cid)],
            )

        return await self._act(p, rid, version, "purchase", build)

    # ---------------------------------------------------------------- Pro Bono (O12-O14)

    async def approve(self, p: Principal, rid: str, version: int, cid: str) -> dict[str, Any]:
        async def build(doc: dict[str, Any], dst: str) -> Change:
            lines = [{**ln, "reservation": {"status": "NONE", "units": []}} for ln in doc["lines"]]
            payload = {"orderId": doc["id"], "lines": _lines_payload(lines)}
            return Change(
                set={"lines": lines, "approval": {"by": actor(p), "at": now()}},
                events=[_event("order.probono_approved", doc, payload, p, cid)],
            )

        return await self._act(p, rid, version, "approve", build)

    async def reject(self, p: Principal, rid: str, version: int, reason: str, cid: str) -> dict[str, Any]:
        async def build(doc: dict[str, Any], dst: str) -> Change:
            return Change(
                set={"rejection": {"by": actor(p), "at": now(), "reason": reason}},
                events=[_move("order.probono_rejected", doc, doc["status"], dst, p, cid, reason)],
                reason=reason,
            )

        return await self._act(p, rid, version, "reject", build)

    # ---------------------------------------------------------------- fulfilment (O9-O11)

    async def pick(self, p: Principal, rid: str, line_id: str, unit: str, key: str, cid: str) -> dict[str, Any]:
        doc = await self._load(rid)
        st = doc["status"]
        if not (
            (doc["type"] == d.PAID and st == "PURCHASING")
            or (doc["type"] == d.PROBONO and st in ("APPROVED", "PICKING"))
        ):
            raise illegal(st, "pick")
        idx = next((i for i, ln in enumerate(doc["lines"]) if ln["lineId"] == line_id), None)
        if idx is None:
            raise invalid("lineId", f"Unknown line {line_id}")
        line = doc["lines"][idx]
        if doc["type"] == d.PAID and line.get("choice") != d.CIMH:
            raise conflict("LINE_NOT_PICKABLE", "Supplier items ship direct to the customer; nothing to pick")
        picked = line.get("picked") or []
        if any(x.get("barcode") == unit for x in picked):
            return self.view(doc, p)  # repeated scan of the same unit
        if len(picked) >= line["qty"]:
            raise conflict("LINE_FULLY_PICKED", "Every unit of this line is already picked")
        if "_" in unit and not unit.startswith(line["productId"] + "_"):
            raise conflict("UNIT_WRONG_PRODUCT", f"This unit is not a {line['product']['name']}")
        await self.deps.pick(unit, rid, p.sub, key)
        t = now()
        update: dict[str, Any] = {
            "$push": {f"lines.{idx}.picked": {"barcode": unit, "pickedby": p.sub, "pickeddate": t}},
            "$set": {"updatedAt": t},
            "$inc": {"version": 1},
        }
        if st == "APPROVED":
            update["$set"] |= {"status": "PICKING", "statusAt": t}
            update["$push"]["history"] = {"from": "APPROVED", "to": "PICKING", "by": actor(p), "at": t, "reason": None}
        res = await self.store.orders.find_one_and_update(
            {"id": rid, "status": st}, update, return_document=ReturnDocument.AFTER
        )
        if res is None:  # status moved meanwhile (e.g. first pick raced): record the pick anyway
            update["$set"] = {k: v for k, v in update["$set"].items() if k not in ("status", "statusAt")}
            update["$push"].pop("history", None)
            res = await self.store.orders.find_one_and_update({"id": rid}, update, return_document=ReturnDocument.AFTER)
        return self.view(res, p)

    async def ship(self, p: Principal, rid: str, version: int, body: dict[str, Any], cid: str) -> dict[str, Any]:
        async def build(doc: dict[str, Any], dst: str) -> Change:
            short = [ln["lineId"] for ln in self._pickable(doc) if len(ln.get("picked") or []) < ln["qty"]]
            if short:
                raise conflict("PICKING_INCOMPLETE", f"Pick every unit first ({', '.join(short)})")
            if body["carrier"] != "HAND" and not (body.get("tracking") or "").strip():
                raise invalid("tracking", "Enter the tracking number", "TRACKING_REQUIRED")
            cost = body.get("cost")
            shipping = {
                "carrier": body["carrier"],
                "tracking": (body.get("tracking") or "").strip() or None,
                "note": body.get("note"),
                "cost": d.to_db(d.money(cost)) if cost else None,
                "date": body["date"],
                "by": actor(p),
            }
            payload = {
                "orderId": doc["id"],
                "customer": doc["customer"],
                "carrier": body["carrier"],
                "tracking": shipping["tracking"],
                "notifyCustomer": body.get("notifyCustomer", True),
            }
            return Change(set={"shipping": shipping}, events=[_event("order.shipped", doc, payload, p, cid)])

        return await self._act(p, rid, version, "ship", build)

    async def deliver(self, p: Principal, rid: str, version: int, body: dict[str, Any], cid: str) -> dict[str, Any]:
        async def build(doc: dict[str, Any], dst: str) -> Change:
            at = body.get("deliveredAt") or now()
            fields: dict[str, Any] = {"deliveredAt": at}
            if body.get("invoiceNumber"):
                fields["invoice"] = {"number": body["invoiceNumber"], "date": at}
            return Change(set=fields, events=[_move("order.delivered", doc, doc["status"], dst, p, cid)])

        return await self._act(p, rid, version, "deliver", build)

    # ================================================================== internal (document-svc) and events

    async def access(self, rid: str, user: str) -> bool:
        doc = await self.store.orders.find_one(
            {"id": rid, "status": {"$ne": d.CART}}, {"customer": 1, "organisationId": 1}
        )
        if doc is None:
            return False
        acc = await self.deps.account(user)
        if not acc or acc.get("status") not in (None, "ACTIVE"):
            return False
        if acc.get("role") in ("staff", "admin") or doc["customer"] == user:
            return True
        org = doc.get("organisationId")
        return bool(org and acc.get("organisationId") == org)

    async def attach_file(self, rid: str, f: dict[str, Any]) -> bool:
        """Idempotent: a file id is attached once. No version bump (a PDF arriving must not break If-Match)."""
        entry = {k: f.get(k) for k in ("id", "kind", "name", "mime", "size", "sha256")}
        entry["uploadedAt"] = aware(f.get("uploadedAt")) or now()
        extra: dict[str, Any] = {}
        if f["kind"] == "agreement":
            extra["agreement.fileId"] = f["id"]
        elif f["kind"] == "cimh_quote":
            extra["cimhQuote.fileId"] = f["id"]
        filt: dict[str, Any] = {"id": rid, "status": {"$ne": d.CART}, "files.id": {"$ne": f["id"]}}
        if f["kind"] == "agreement":
            filt["agreement"] = {"$ne": None}
        if f["kind"] == "cimh_quote":
            filt["cimhQuote"] = {"$ne": None}
        res = await self.store.orders.update_one(filt, {"$push": {"files": entry}, "$set": extra})
        if res.matched_count == 0 and extra:  # no agreement/quote to point at: still keep the file
            res = await self.store.orders.update_one(
                {"id": rid, "status": {"$ne": d.CART}, "files.id": {"$ne": f["id"]}}, {"$push": {"files": entry}}
            )
        return bool(res.modified_count)

    async def stock_reserved(self, payload: dict[str, Any]) -> bool:
        doc = await self.store.orders.find_one({"id": payload["orderId"]})
        if doc is None:
            return False
        units = {x["lineId"]: list(x.get("units") or []) for x in payload["lines"]}
        lines = [
            {**ln, "reservation": {"status": "RESERVED", "units": units[ln["lineId"]]}} if ln["lineId"] in units else ln
            for ln in doc["lines"]
        ]
        await self.store.orders.update_one({"_id": doc["_id"]}, {"$set": {"lines": lines}})
        return True

    async def stock_reservation_failed(self, payload: dict[str, Any]) -> bool:
        doc = await self.store.orders.find_one({"id": payload["orderId"]})
        if doc is None:
            return False
        short = {x["lineId"] for x in payload["lines"]}
        lines = []
        for ln in doc["lines"]:
            if isinstance(ln.get("reservation"), dict):
                status = "FAILED" if ln["lineId"] in short else "NONE"
                ln = {**ln, "reservation": {"status": status, "units": []}}
            lines.append(ln)
        await self.store.orders.update_one({"_id": doc["_id"]}, {"$set": {"lines": lines}})
        return True

    async def stock_released(self, payload: dict[str, Any]) -> bool:
        doc = await self.store.orders.find_one({"id": payload["orderId"]})
        if doc is None:
            return False
        lines = [
            {**ln, "reservation": {**ln["reservation"], "status": "RELEASED"}}
            if isinstance(ln.get("reservation"), dict) and ln["reservation"].get("status") == "RESERVED"
            else ln
            for ln in doc["lines"]
        ]
        await self.store.orders.update_one({"_id": doc["_id"]}, {"$set": {"lines": lines}})
        return True

    # ================================================================== jobs

    async def expire_quotes(self, batch: int = 200) -> int:
        """QUOTED / AWAITING_AGREEMENT past the quote expiry -> CANCELLED (auto), order.expired published."""
        t = now()
        docs = (
            await self.store.orders.find({"status": {"$in": list(d.QUOTE_LIVE)}, "quoteExpiresAt": {"$lt": t}})
            .limit(batch)
            .to_list()
        )
        n = 0
        for doc in docs:
            src = doc["status"]
            reason = "Quote expired"
            event = _move("order.expired", doc, src, "CANCELLED", None, doc["id"], reason)
            res = await self.store.orders.update_one(
                {"_id": doc["_id"], "status": src, "version": doc["version"]},
                {
                    "$set": {
                        "status": "CANCELLED",
                        "updatedAt": t,
                        "statusAt": t,
                        "cancellation": {"by": SYSTEM, "at": t, "reason": reason, "auto": True},
                    },
                    "$inc": {"version": 1},
                    "$push": {
                        "history": {"from": src, "to": "CANCELLED", "by": SYSTEM, "at": t, "reason": reason},
                        "outbox": event.model_dump(mode="python"),
                    },
                },
            )
            n += res.modified_count
        return n

    async def purge_carts(self, days: int = 180, batch: int = 500) -> int:
        """Carts untouched for `days` are emptied (business rule)."""
        cutoff = now() - timedelta(days=days)
        res = await self.store.orders.update_many(
            {"status": d.CART, "updatedAt": {"$lt": cutoff}, "lines.0": {"$exists": True}},
            {"$set": {"lines": [], "updatedAt": now()}, "$inc": {"version": 1}},
        )
        return int(res.modified_count)
