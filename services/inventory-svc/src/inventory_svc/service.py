"""inventory-svc business rules (PRD I1-I11; BSD §5.8, §5.9, §5.11; API inventory.openapi.yaml; TAD §7.3-7.4).

Every scan is ONE transaction: the unit update, its `history` row and the product's `stock` document (counts
recomputed from `storage`, plus the outbox events) commit together, so counts always reconcile with units and
history, and no event is published for a change that didn't happen.
"""

from __future__ import annotations

import json
import secrets
from datetime import UTC, datetime
from typing import Any

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from cimh_common.auth import Principal
from cimh_common.errors import ProblemError, conflict, not_found
from cimh_common.outbox import OutboxEvent, new_event, outbox_push
from cimh_common.paging import clamp_limit, decode_cursor, encode_cursor, page

from .places import Places
from .store import AVAILABLE, SET, Store, now

UNIT_SEP = "_"  # legacy unit barcode: <productId>_<code>
OPERATIONS = ("stow", "pick", "relocate", "assign", "unassign", "reserve", "release", "adjust")
LEGACY_OPERATIONS = {"orderpick": "pick", "selfstow": "assign"}


# ---------------------------------------------------------------- views


def iso(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return str(value.astimezone(UTC).isoformat().replace("+00:00", "Z"))
    return str(value)


def _s(value: Any) -> str | None:
    """Legacy rows use "" for empty; the API uses null."""
    return str(value) if value not in (None, "") else None


def unit_view(doc: dict[str, Any], product_name: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "barcode": doc["barcode"],
        "product": doc.get("product") or "",
        "serial": _s(doc.get("serial")),
        "site": _s(doc.get("site")),
        "siteName": _s(doc.get("sitename")),
        "location": _s(doc.get("location")),
        "locationName": _s(doc.get("locationname")),
        "shelf": _s(doc.get("shelf")),
        "shelfNumber": doc.get("shelfnumber") if isinstance(doc.get("shelfnumber"), int) else None,
        "stowed": bool(doc.get("stowed")),
        "stowBy": _s(doc.get("stowby")),
        "stowDate": iso(doc.get("stowdate")),
        "picked": bool(doc.get("picked")),
        "pickedBy": _s(doc.get("pickedby")),
        "pickedDate": iso(doc.get("pickeddate")),
        "pickedReason": _s(doc.get("pickedreason")),
        "orderId": _s(doc.get("orderid")),
        "reservedFor": _s(doc.get("reservedFor")),
        "assignedTo": _s(doc.get("assignedTo")),
        "images": [str(i) for i in doc.get("images") or [] if isinstance(i, str)],
    }
    if product_name:
        out["productName"] = product_name
    return out


def history_view(doc: dict[str, Any]) -> dict[str, Any]:
    op = str(doc.get("operation") or "adjust")
    op = LEGACY_OPERATIONS.get(op, op)
    frm = doc.get("from")
    return {
        "unit": str(doc.get("id") or ""),
        "operation": op if op in OPERATIONS else "adjust",
        "reason": _s(doc.get("reason")),
        "site": _s(doc.get("site")),
        "location": _s(doc.get("location")),
        "shelf": _s(doc.get("shelf")),
        "from": frm if isinstance(frm, dict) else None,
        "user": str(doc.get("user") or ""),
        "accountId": _s(doc.get("accountId")),
        "orderId": _s(doc.get("orderId")),
        "date": iso(doc.get("date")) or "",
    }


def site_view(d: dict[str, Any]) -> dict[str, Any]:
    out = {"barcode": d["barcode"], "name": d.get("name") or d["barcode"], "active": bool(d.get("active", True))}
    out["country"] = d.get("country") or ""
    for k in ("address", "description"):
        if d.get(k):
            out[k] = d[k]
    return out


def shelf_view(d: dict[str, Any], site_name: str | None, location_name: str | None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "barcode": d["barcode"],
        "number": int(d.get("number") or 0),
        "site": d.get("site") or "",
        "location": d.get("location") or "",
    }
    if site_name:
        out["siteName"] = site_name
    if location_name:
        out["locationName"] = location_name
    return out


def is_low(available: int, threshold: int, active: bool) -> bool:
    """Low = at or below a set threshold (0 = no alert) on an active product."""
    return active and threshold > 0 and available <= threshold


def _hex() -> str:
    return secrets.token_hex(16)


class _Short(Exception):
    def __init__(self, lines: list[dict[str, Any]]) -> None:
        super().__init__("short")
        self.lines = lines


class InventoryService:
    def __init__(self, store: Store, places: Places, redis: Any = None, *, cache_seconds: int = 600) -> None:
        self.store = store
        self.places = places
        self.redis = redis
        self.cache_seconds = cache_seconds

    # ------------------------------------------------------------------ places (I1)

    async def _place(self, barcode: str) -> dict[str, Any] | None:
        key = f"inv:place:{barcode}"
        if self.redis is not None:
            raw = await self.redis.get(key)
            if raw is not None:
                cached: dict[str, Any] | None = json.loads(raw)
                return cached
        found = await self.places.list(barcode=barcode)
        place = found[0] if found else None
        if self.redis is not None:
            await self.redis.set(key, json.dumps(place), ex=self.cache_seconds if place else 30)
        return place

    async def _remember(self, place: dict[str, Any]) -> None:
        if self.redis is not None:
            await self.redis.set(f"inv:place:{place['barcode']}", json.dumps(place), ex=self.cache_seconds)

    async def shelf(self, barcode: str) -> dict[str, Any]:
        place = await self._place(barcode)
        if not place or place.get("kind") != "shelf" or not place.get("active", True):
            raise ProblemError(404, "SHELF_NOT_FOUND", "No shelf with this barcode")
        site = await self._place(place.get("site") or "")
        location = await self._place(place.get("location") or "")
        return shelf_view(place, (site or {}).get("name"), (location or {}).get("name"))

    async def sites(self) -> list[dict[str, Any]]:
        return [site_view(d) for d in await self.places.list(kind="site")]

    async def create_site(self, p: Principal, body: dict[str, Any]) -> dict[str, Any]:
        place = await self.places.put({"kind": "site", "barcode": f"SITE{_hex()}", "active": True, **body})
        await self._remember(place)
        return site_view(place)

    async def _require(self, barcode: str, kind: str) -> dict[str, Any]:
        place = await self._place(barcode)
        if not place or place.get("kind") != kind:
            raise not_found(f"No {kind} with this barcode")
        return place

    async def locations(self, site: str, with_shelves: bool) -> list[dict[str, Any]]:
        locs = await self.places.list(kind="location", site=site)
        shelves = await self.places.list(kind="shelf", site=site)
        site_doc = await self._place(site)
        by_loc: dict[str, list[dict[str, Any]]] = {}
        for sh in shelves:
            by_loc.setdefault(sh.get("location") or "", []).append(sh)
        out = []
        for loc in locs:
            mine = sorted(by_loc.get(loc["barcode"], []), key=lambda x: int(x.get("number") or 0))
            item: dict[str, Any] = {
                "barcode": loc["barcode"],
                "name": loc.get("name") or loc["barcode"],
                "site": loc.get("site") or site,
                "description": loc.get("description"),
                "active": bool(loc.get("active", True)),
                "shelfCount": len(mine),
            }
            if with_shelves:
                item["shelves"] = [shelf_view(s, (site_doc or {}).get("name"), item["name"]) for s in mine]
            out.append(item)
        return sorted(out, key=lambda x: str(x["name"]).lower())

    async def create_location(self, p: Principal, site: str, body: dict[str, Any]) -> dict[str, Any]:
        await self._require(site, "site")
        place = await self.places.put(
            {"kind": "location", "barcode": f"LOC{_hex()}", "site": site, "active": True, **body}
        )
        await self._remember(place)
        return {
            "barcode": place["barcode"],
            "name": place["name"],
            "site": site,
            "description": place.get("description"),
            "active": True,
            "shelfCount": 0,
        }

    async def add_shelves(self, p: Principal, location: str, count: int) -> list[dict[str, Any]]:
        loc = await self._require(location, "location")
        site = await self._place(loc.get("site") or "")
        existing = await self.places.list(kind="shelf", location=location)
        start = max((int(s.get("number") or 0) for s in existing), default=0)
        out = []
        for n in range(start + 1, start + count + 1):
            place = await self.places.put(
                {
                    "kind": "shelf",
                    "barcode": f"SHEL{_hex()}",
                    "name": f"{loc.get('name') or location} {n}",
                    "number": n,
                    "site": loc.get("site"),
                    "location": location,
                    "active": True,
                }
            )
            await self._remember(place)
            out.append(shelf_view(place, (site or {}).get("name"), loc.get("name")))
        return out

    # ------------------------------------------------------------------ units (I2, I7)

    async def _product_name(self, product_id: str) -> str | None:
        doc = await self.store.stock.find_one({"id": product_id}, {"productName": 1})
        return (doc or {}).get("productName")

    async def view(self, doc: dict[str, Any]) -> dict[str, Any]:
        return unit_view(doc, await self._product_name(doc.get("product") or ""))

    async def views(self, docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Unit views for a page, with product names from ONE query."""
        ids = list({d.get("product") or "" for d in docs})
        found = await self.store.stock.find({"id": {"$in": ids}}, {"id": 1, "productName": 1}).to_list()
        names = {f["id"]: f.get("productName") for f in found}
        return [unit_view(d, names.get(d.get("product") or "")) for d in docs]

    async def unit(self, barcode: str) -> dict[str, Any]:
        doc = await self.store.storage.find_one({"barcode": barcode})
        if doc is None:
            raise ProblemError(404, "UNIT_NOT_FOUND", "No unit with this barcode")
        return await self.view(doc)

    async def shelf_units(
        self, barcode: str, cursor: str | None, limit: int | None
    ) -> tuple[list[dict[str, Any]], str | None]:
        await self.shelf(barcode)
        docs, nxt = await page(
            self.store.storage,
            {"shelf": barcode, "stowed": True},
            sort_field="barcode",
            id_field="barcode",
            cursor=cursor,
            limit=limit,
        )
        return await self.views(docs), nxt

    async def _known_product(self, product_id: str) -> bool:
        """True if the product exists. The `stock` copy normally comes from catalog events; if it isn't there
        yet (event still in flight, or a product older than the consumer) ask catalog-svc once and create it."""
        if await self.store.stock.find_one({"id": product_id}, {"_id": 1}):
            return True
        found = [d for d in await self.places.products([product_id]) if d.get("id") == product_id]
        if not found:
            return False
        d = found[0]
        counts = await self._counts(product_id, None)
        threshold, active = int(d.get("threshold") or 0), bool(d.get("active", True))
        fields = {"productName": d.get("name"), "type": d.get("type"), "threshold": threshold, "active": active}
        fields |= {**counts, "low": is_low(counts["available"], threshold, active), "updatedAt": now()}
        # $setOnInsert: if the consumer got there first, its copy wins.
        await self.store.stock.update_one({"id": product_id}, {"$setOnInsert": fields}, upsert=True)
        return True

    async def labels(self, p: Principal, product_id: str, quantity: int, serials: list[str] | None) -> dict[str, Any]:
        if not await self._known_product(product_id):
            raise not_found("Product not found")
        if serials is not None and len(serials) != quantity:
            raise ProblemError(
                422, "VALIDATION_FAILED", errors=[{"field": "serials", "message": "one serial per unit"}]
            )
        t = now()
        barcodes: list[str] = []
        for i in range(quantity):
            for _ in range(5):  # 32-bit code per product: a clash is rare, retry it
                code = f"{product_id}{UNIT_SEP}{secrets.token_hex(4)}"
                try:
                    await self.store.storage.insert_one(
                        {
                            "barcode": code,
                            "product": product_id,
                            "serial": serials[i] if serials else None,
                            "stowed": False,
                            "picked": False,
                            "images": [],
                            "createdBy": p.sub,
                            "createdAt": t,
                            "updatedAt": t,
                        }
                    )
                except DuplicateKeyError:
                    continue
                barcodes.append(code)
                break
            else:  # pragma: no cover - five 32-bit clashes in a row
                raise ProblemError(503, "DEPENDENCY_UNAVAILABLE", "Could not allocate unit barcodes; try again")
        # The printable PDF/CSV comes from document-svc (P6); until then the screen renders the codes itself.
        return {"barcodes": barcodes, "fileId": None}

    async def _unit_for_scan(self, barcode: str, s: Any) -> dict[str, Any]:
        doc = await self.store.storage.find_one({"barcode": barcode}, session=s)
        if doc is not None:
            return dict(doc)
        # Legacy labels (<productId>_<code>) were printed without a storage record; the first stow creates it.
        product_id, sep, code = barcode.rpartition(UNIT_SEP)
        if sep and code and product_id and await self.store.stock.find_one({"id": product_id}, session=s):
            t = now()
            new: dict[str, Any] = {
                "barcode": barcode,
                "product": product_id,
                "serial": None,
                "stowed": False,
                "picked": False,
            }
            new |= {"images": [], "createdAt": t, "updatedAt": t}
            await self.store.storage.insert_one(new, session=s)
            return new
        raise ProblemError(404, "UNIT_NOT_FOUND", "No unit with this barcode")

    # ------------------------------------------------------------------ stock bookkeeping (I8)

    async def _counts(self, product_id: str, s: Any) -> dict[str, int]:
        c = self.store.storage.count_documents
        base = {"product": product_id}
        return {
            "available": await c({**base, **AVAILABLE}, session=s),
            "reserved": await c({**base, "stowed": True, "picked": False, "reservedFor": SET}, session=s),
            "picked": await c({**base, "picked": True}, session=s),
            "assigned": await c({**base, "assignedTo": SET}, session=s),
        }

    async def _sync_stock(
        self, product_id: str, s: Any, cid: str, actor: str | None, extra: list[OutboxEvent] | None = None
    ) -> None:
        """Recount one product from `storage`; publish stock.changed (+ stock.low on crossing) with `extra`."""
        counts = await self._counts(product_id, s)
        doc = await self.store.stock.find_one({"id": product_id}, session=s) or {}
        threshold = int(doc.get("threshold") or 0)
        low = is_low(counts["available"], threshold, bool(doc.get("active", True)))
        events = list(extra or [])
        if any(doc.get(k) != v for k, v in counts.items()):
            events.append(
                new_event(
                    "stock.changed",
                    {"productId": product_id, "available": counts["available"], "reserved": counts["reserved"]},
                    correlation_id=cid,
                    actor_id=actor,
                )
            )
        if low and not doc.get("low"):
            payload = {"productId": product_id, "available": counts["available"], "threshold": threshold}
            events.append(new_event("stock.low", payload, correlation_id=cid, actor_id=actor))
        update: dict[str, Any] = {
            "$set": {**counts, "low": low, "updatedAt": now()},
            "$setOnInsert": {"threshold": 0, "active": True},
        }
        if events:
            update |= outbox_push(*events)
        await self.store.stock.update_one({"id": product_id}, update, upsert=True, session=s)

    def _unit_event(self, kind: str, doc: dict[str, Any], p: Principal, cid: str, **extra: Any) -> OutboxEvent:
        payload = {"barcode": doc["barcode"], "productId": doc["product"], "by": p.sub}
        payload |= {"shelf": extra.get("shelf"), "orderId": extra.get("orderId"), "reason": extra.get("reason")}
        return new_event(f"unit.{kind}", payload, correlation_id=cid, actor_id=p.sub)

    async def _log(self, s: Any, unit: dict[str, Any], operation: str, user: str, **fields: Any) -> None:
        row = {"id": unit["barcode"], "operation": operation, "user": user, "date": now()}
        row |= {k: v for k, v in fields.items() if v is not None}
        await self.store.history.insert_one(row, session=s)

    @staticmethod
    def _where(doc: dict[str, Any]) -> dict[str, Any]:
        return {"site": doc.get("site"), "location": doc.get("location"), "shelf": doc.get("shelf")}

    @staticmethod
    def _on_shelf(shelf: dict[str, Any]) -> dict[str, Any]:
        return {
            "site": shelf["site"],
            "sitename": shelf.get("siteName"),
            "location": shelf["location"],
            "locationname": shelf.get("locationName"),
            "shelf": shelf["barcode"],
            "shelfnumber": shelf["number"],
        }

    # ------------------------------------------------------------------ scans (I3-I6)

    async def stow(self, p: Principal, barcode: str, shelf_code: str, cid: str) -> dict[str, Any]:
        shelf = await self.shelf(shelf_code)
        product_id, sep, _ = barcode.rpartition(UNIT_SEP)
        if sep and product_id and not await self.store.storage.find_one({"barcode": barcode}, {"_id": 1}):
            await self._known_product(product_id)  # a legacy label: make sure the product's copy exists

        async def tx(s: Any) -> dict[str, Any]:
            doc = await self._unit_for_scan(barcode, s)
            if doc.get("assignedTo"):
                raise conflict("UNIT_ASSIGNED", f"Issued to {doc['assignedTo']}: return it first")
            if doc.get("picked") and _s(doc.get("orderid")):
                raise conflict("UNIT_ALREADY_PICKED", f"Picked for request {doc['orderid']}; it can't be re-stowed")
            if doc.get("stowed"):
                if doc.get("shelf") == shelf["barcode"]:
                    return doc  # same scan twice: nothing to do
                where = f"{doc.get('locationname') or doc.get('location')} shelf {doc.get('shelfnumber')}"
                raise conflict("UNIT_ALREADY_STOWED", f"Already stowed at {where}; use relocate to move it")
            t = now()
            fields = self._on_shelf(shelf) | {"stowed": True, "stowby": p.sub, "stowdate": t, "picked": False}
            fields |= {"pickedby": None, "pickeddate": None, "pickedreason": None, "updatedAt": t}
            res = await self.store.storage.find_one_and_update(
                {"_id": doc["_id"], "stowed": {"$ne": True}},
                {"$set": fields},
                return_document=ReturnDocument.AFTER,
                session=s,
            )
            if res is None:
                raise conflict("UNIT_ALREADY_STOWED", "The unit was stowed by someone else just now")
            await self._log(s, res, "stow", p.sub, **self._where(res))
            event = self._unit_event("stowed", res, p, cid, shelf=shelf["barcode"])
            await self._sync_stock(res["product"], s, cid, p.sub, [event])
            return dict(res)

        return await self.view(await self.store.transaction(tx))

    async def pick(
        self, p: Principal, barcode: str, reason: str | None, order_id: str | None, cid: str
    ) -> dict[str, Any]:
        async def tx(s: Any) -> dict[str, Any]:
            doc = await self.store.storage.find_one({"barcode": barcode}, session=s)
            if doc is None:
                raise ProblemError(404, "UNIT_NOT_FOUND", "No unit with this barcode")
            if doc.get("picked"):
                raise conflict("UNIT_ALREADY_PICKED", "This unit was already picked")
            if doc.get("assignedTo"):
                raise conflict("UNIT_ASSIGNED", f"Issued to {doc['assignedTo']}: return it first")
            if not doc.get("stowed"):
                raise conflict("UNIT_NOT_STOWED", "This unit is not on a shelf")
            reserved = _s(doc.get("reservedFor"))
            if order_id and reserved != order_id:
                raise conflict("UNIT_NOT_RESERVED_FOR_ORDER", f"This unit is not reserved for {order_id}")
            if not order_id and reserved:
                raise conflict("UNIT_RESERVED", f"Reserved for request {reserved}; pick it for that request")
            t = now()
            fields = {"stowed": False, "picked": True, "pickedby": p.sub, "pickeddate": t, "updatedAt": t}
            fields |= {"pickedreason": reason}
            if order_id:
                fields["orderid"] = order_id
            res = await self.store.storage.find_one_and_update(
                {"_id": doc["_id"], "stowed": True, "picked": False},
                {"$set": fields},
                return_document=ReturnDocument.AFTER,
                session=s,
            )
            if res is None:
                raise conflict("UNIT_ALREADY_PICKED", "The unit was picked by someone else just now")
            await self._log(s, res, "pick", p.sub, reason=reason, orderId=order_id, **self._where(res))
            event = self._unit_event("picked", res, p, cid, shelf=res.get("shelf"), orderId=order_id, reason=reason)
            await self._sync_stock(res["product"], s, cid, p.sub, [event])
            return dict(res)

        return await self.view(await self.store.transaction(tx))

    async def relocate(self, p: Principal, barcode: str, to_shelf: str, cid: str) -> dict[str, Any]:
        shelf = await self.shelf(to_shelf)

        async def tx(s: Any) -> dict[str, Any]:
            doc = await self.store.storage.find_one({"barcode": barcode}, session=s)
            if doc is None:
                raise ProblemError(404, "UNIT_NOT_FOUND", "No unit with this barcode")
            if doc.get("picked"):
                raise conflict("UNIT_ALREADY_PICKED", "This unit was already picked")
            if doc.get("assignedTo"):
                raise conflict("UNIT_ASSIGNED", f"Issued to {doc['assignedTo']}: return it first")
            if not doc.get("stowed"):
                raise conflict("UNIT_NOT_STOWED", "This unit is not on a shelf; stow it instead")
            if doc.get("shelf") == shelf["barcode"]:
                return dict(doc)
            res = await self.store.storage.find_one_and_update(
                {"_id": doc["_id"], "stowed": True, "shelf": doc.get("shelf")},
                {"$set": self._on_shelf(shelf) | {"updatedAt": now()}},
                return_document=ReturnDocument.AFTER,
                session=s,
            )
            if res is None:
                raise conflict("UNIT_NOT_STOWED", "The unit moved meanwhile; scan it again")
            await self._log(s, res, "relocate", p.sub, **self._where(res), **{"from": self._where(doc)})
            return dict(res)

        return await self.view(await self.store.transaction(tx))

    async def assign(self, p: Principal, barcode: str, account_id: str, cid: str) -> dict[str, Any]:
        async def tx(s: Any) -> dict[str, Any]:
            doc = await self.store.storage.find_one({"barcode": barcode}, session=s)
            if doc is None:
                raise ProblemError(404, "UNIT_NOT_FOUND", "No unit with this barcode")
            if doc.get("picked"):
                raise conflict("UNIT_ALREADY_PICKED", "This unit was already picked")
            if _s(doc.get("reservedFor")):
                raise conflict("UNIT_RESERVED", f"Reserved for request {doc['reservedFor']}")
            if doc.get("assignedTo") == account_id:
                return dict(doc)
            if doc.get("assignedTo"):
                raise conflict("UNIT_ASSIGNED", f"Issued to {doc['assignedTo']}: return it first")
            res = await self.store.storage.find_one_and_update(
                {"_id": doc["_id"], "picked": False, "assignedTo": {"$in": [None, ""]}},
                {"$set": {"assignedTo": account_id, "stowed": False, "updatedAt": now()}},
                return_document=ReturnDocument.AFTER,
                session=s,
            )
            if res is None:
                raise conflict("UNIT_ASSIGNED", "The unit was issued by someone else just now")
            frm = self._where(doc) if doc.get("stowed") else None
            await self._log(s, res, "assign", p.sub, accountId=account_id, **{"from": frm})
            await self._sync_stock(res["product"], s, cid, p.sub)
            return dict(res)

        return await self.view(await self.store.transaction(tx))

    async def unassign(self, p: Principal, barcode: str, cid: str) -> dict[str, Any]:
        async def tx(s: Any) -> dict[str, Any]:
            doc = await self.store.storage.find_one({"barcode": barcode}, session=s)
            if doc is None:
                raise ProblemError(404, "UNIT_NOT_FOUND", "No unit with this barcode")
            holder = _s(doc.get("assignedTo"))
            if not holder:
                raise conflict("UNIT_NOT_ASSIGNED", "This unit is not issued to anyone")
            res = await self.store.storage.find_one_and_update(
                {"_id": doc["_id"], "assignedTo": holder},
                {"$unset": {"assignedTo": ""}, "$set": {"updatedAt": now()}},
                return_document=ReturnDocument.AFTER,
                session=s,
            )
            if res is None:
                raise conflict("UNIT_NOT_ASSIGNED", "The unit was returned by someone else just now")
            await self._log(s, res, "unassign", p.sub, accountId=holder)
            await self._sync_stock(res["product"], s, cid, p.sub)
            return dict(res)

        return await self.view(await self.store.transaction(tx))

    # ------------------------------------------------------------------ stock reads (I8, I4, I10)

    async def product_stock(self, product_id: str) -> dict[str, Any]:
        doc = await self.store.stock.find_one({"id": product_id}) or {}
        counts = (
            {k: int(doc.get(k) or 0) for k in ("available", "reserved", "picked", "assigned")}
            if "available" in doc
            else await self._counts(product_id, None)
        )
        cursor = await self.store.storage.aggregate(
            [
                {"$match": {"product": product_id, "stowed": True, "picked": False}},
                {
                    "$group": {
                        "_id": {"site": "$site", "location": "$location", "shelf": "$shelf"},
                        "count": {"$sum": 1},
                        "siteName": {"$first": "$sitename"},
                        "locationName": {"$first": "$locationname"},
                        "shelfNumber": {"$first": "$shelfnumber"},
                    }
                },
                {"$sort": {"locationName": 1, "shelfNumber": 1}},
            ]
        )
        by_location = []
        for g in await cursor.to_list():
            row: dict[str, Any] = {
                "site": g["_id"].get("site") or "",
                "location": g["_id"].get("location") or "",
                "shelf": g["_id"].get("shelf") or "",
                "count": int(g["count"]),
            }
            for k in ("siteName", "locationName"):
                if g.get(k):
                    row[k] = g[k]
            if isinstance(g.get("shelfNumber"), int):
                row["shelfNumber"] = g["shelfNumber"]
            by_location.append(row)
        out: dict[str, Any] = {
            "productId": product_id,
            **counts,
            "threshold": int(doc.get("threshold") or 0),
            "byLocation": by_location,
        }
        if doc.get("productName"):
            out["productName"] = doc["productName"]
        return out

    async def low_stock(self, cursor: str | None, limit: int | None) -> tuple[list[dict[str, Any]], str | None]:
        docs, nxt = await page(self.store.stock, {"low": True}, sort_field="productName", cursor=cursor, limit=limit)
        items = []
        for d in docs:
            item = {"productId": d["id"], "threshold": int(d.get("threshold") or 0), "byLocation": []}
            item |= {k: int(d.get(k) or 0) for k in ("available", "reserved", "picked", "assigned")}
            if d.get("productName"):
                item["productName"] = d["productName"]
            items.append(item)
        return items, nxt

    async def assignments(
        self, account_id: str | None, cursor: str | None, limit: int | None
    ) -> tuple[list[dict[str, Any]], str | None]:
        q: dict[str, Any] = {"assignedTo": account_id} if account_id else {"assignedTo": SET}
        docs, nxt = await page(
            self.store.storage, q, sort_field="assignedTo", id_field="barcode", cursor=cursor, limit=limit
        )
        return await self.views(docs), nxt

    async def history(
        self, filters: dict[str, Any], cursor: str | None, limit: int | None
    ) -> tuple[list[dict[str, Any]], str | None]:
        """Newest first, paged on (date, _id)."""
        n = clamp_limit(limit)
        q: dict[str, Any] = {}
        if filters.get("unit"):
            q["id"] = filters["unit"]
        if filters.get("user"):
            q["user"] = filters["user"]
        if filters.get("operation"):
            q["operation"] = filters["operation"]
        dates = {op: filters[k] for k, op in (("from", "$gte"), ("to", "$lte")) if filters.get(k)}
        if dates:
            q["date"] = dates
        if cursor:
            value, oid = decode_cursor(cursor)
            try:
                at, last = datetime.fromisoformat(str(value)), ObjectId(oid)
            except Exception as exc:
                raise ProblemError(422, "VALIDATION_FAILED", "invalid cursor") from exc
            q = {"$and": [q, {"$or": [{"date": {"$lt": at}}, {"date": at, "_id": {"$lt": last}}]}]}
        docs = await self.store.history.find(q).sort([("date", -1), ("_id", -1)]).limit(n + 1).to_list()
        nxt = None
        if len(docs) > n:
            docs = docs[:n]
            last_doc = docs[-1]
            nxt = encode_cursor(iso(last_doc["date"]), str(last_doc["_id"]))
        return [history_view(d) for d in docs], nxt

    # ------------------------------------------------------------------ internal: availability, reservations (I9, I11)

    async def availability(self, lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out = []
        for line in lines:
            n = await self.store.storage.count_documents({"product": line["productId"], **AVAILABLE})
            out.append({"lineId": line["lineId"], "available": n, "fullQuantity": n >= line["qty"]})
        return out

    @staticmethod
    def _by_line(lines: list[dict[str, Any]], units: list[dict[str, Any]]) -> list[dict[str, Any]]:
        pool: dict[str, list[str]] = {}
        for u in sorted(units, key=lambda x: x["barcode"]):
            pool.setdefault(u["product"], []).append(u["barcode"])
        out = []
        for line in lines:
            mine = pool.get(line["productId"], [])
            out.append({"lineId": line["lineId"], "units": mine[: line["qty"]]})
            pool[line["productId"]] = mine[line["qty"] :]
        return out

    async def reserve(self, p: Principal, order_id: str, lines: list[dict[str, Any]], cid: str) -> list[dict[str, Any]]:
        """All lines or nothing, in one transaction (TAD §7.3). Repeating a reservation returns the first one."""
        held = await self.store.storage.find({"reservedFor": order_id}, {"barcode": 1, "product": 1}).to_list()
        if held:
            return self._by_line(lines, held)
        products = list(dict.fromkeys(line["productId"] for line in lines))

        async def tx(s: Any) -> list[dict[str, Any]]:
            t = now()
            short: list[dict[str, Any]] = []
            taken: list[dict[str, Any]] = []
            for line in lines:
                found = (
                    await self.store.storage.find(
                        {"product": line["productId"], **AVAILABLE}, {"_id": 1, "barcode": 1, "product": 1}, session=s
                    )
                    .limit(line["qty"])
                    .to_list()
                )
                if len(found) < line["qty"]:
                    short.append({"lineId": line["lineId"], "requested": line["qty"], "available": len(found)})
                    continue
                res = await self.store.storage.update_many(
                    {"_id": {"$in": [d["_id"] for d in found]}, "reservedFor": None},
                    {"$set": {"reservedFor": order_id, "reservedAt": t, "updatedAt": t}},
                    session=s,
                )
                if res.modified_count != line["qty"]:
                    short.append({"lineId": line["lineId"], "requested": line["qty"], "available": res.modified_count})
                taken += found
            if short:
                raise _Short(short)
            for u in taken:
                await self._log(s, u, "reserve", p.sub, orderId=order_id)
            result = self._by_line(lines, taken)
            reserved = new_event(
                "stock.reserved", {"orderId": order_id, "lines": result}, correlation_id=cid, actor_id=p.sub
            )
            for i, pid in enumerate(products):
                await self._sync_stock(pid, s, cid, p.sub, [reserved] if i == 0 else None)
            return result

        try:
            return await self.store.transaction(tx)
        except _Short as exc:
            # Without a transaction (unit-test mock) undo what this attempt reserved; with one it was rolled back.
            await self.store.storage.update_many(
                {"reservedFor": order_id}, {"$unset": {"reservedFor": "", "reservedAt": ""}}
            )
            failed = new_event(
                "stock.reservation_failed",
                {"orderId": order_id, "lines": exc.lines},
                correlation_id=cid,
                actor_id=p.sub,
            )
            await self.store.stock.update_one(
                {"id": products[0]},
                {"$setOnInsert": {"threshold": 0, "active": True}} | outbox_push(failed),
                upsert=True,
            )
            errors = [
                {"field": x["lineId"], "message": f"requested {x['requested']}, available {x['available']}"}
                for x in exc.lines
            ]
            raise ProblemError(
                409, "RESERVATION_FAILED", "Not enough stock; nothing was reserved", errors=errors
            ) from None

    async def release(self, p: Principal, order_id: str, cid: str) -> int:
        async def tx(s: Any) -> int:
            units = await self.store.storage.find(
                {"reservedFor": order_id, "picked": False}, {"_id": 1, "barcode": 1, "product": 1}, session=s
            ).to_list()
            if not units:
                return 0
            await self.store.storage.update_many(
                {"_id": {"$in": [u["_id"] for u in units]}},
                {"$unset": {"reservedFor": "", "reservedAt": ""}, "$set": {"updatedAt": now()}},
                session=s,
            )
            for u in units:
                await self._log(s, u, "release", p.sub, orderId=order_id)
            released = new_event(
                "stock.released",
                {"orderId": order_id, "units": sorted(u["barcode"] for u in units)},
                correlation_id=cid,
                actor_id=p.sub,
            )
            for i, pid in enumerate(dict.fromkeys(u["product"] for u in units)):
                await self._sync_stock(pid, s, cid, p.sub, [released] if i == 0 else None)
            return len(units)

        return await self.store.transaction(tx)

    # ------------------------------------------------------------------ catalog events (consumer)

    async def product_upserted(self, payload: dict[str, Any], occurred_at: datetime, cid: str) -> bool:
        """Copy name/type/threshold/active from catalog-svc; an older event never overwrites a newer one."""
        pid = payload["productId"]
        doc = await self.store.stock.find_one({"id": pid})
        if doc is not None and doc.get("catalogAt") and doc["catalogAt"] > occurred_at:
            return False
        threshold, active = int(payload.get("threshold") or 0), bool(payload.get("active", True))
        counts = (
            {k: int(doc.get(k) or 0) for k in ("available", "reserved", "picked", "assigned")}
            if doc is not None and "available" in doc
            else await self._counts(pid, None)
        )
        low = is_low(counts["available"], threshold, active)
        fields = {"productName": payload.get("name"), "type": payload.get("type"), "threshold": threshold}
        fields |= {"active": active, "catalogAt": occurred_at, "low": low, "updatedAt": now(), **counts}
        update: dict[str, Any] = {"$set": fields}
        if low and not (doc or {}).get("low"):
            event = new_event(
                "stock.low",
                {"productId": pid, "available": counts["available"], "threshold": threshold},
                correlation_id=cid,
            )
            update |= outbox_push(event)
        if doc is None:
            await self.store.stock.update_one({"id": pid}, update, upsert=True)
        else:
            await self.store.stock.update_one(
                {"id": pid, "$or": [{"catalogAt": {"$exists": False}}, {"catalogAt": {"$lte": occurred_at}}]}, update
            )
        return True

    async def product_deleted(self, payload: dict[str, Any], occurred_at: datetime) -> bool:
        res = await self.store.stock.update_one(
            {"id": payload["productId"]},
            {"$set": {"active": False, "low": False, "catalogAt": occurred_at, "updatedAt": now()}},
        )
        return bool(res.modified_count)
