"""catalog-svc business rules (PRD C1-C8, BSD §5.5-5.7, API catalog.openapi.yaml).

Every product change is ONE conditional update (id + version) that also pushes its outbox event, so state and
event can't diverge (TAD §5). Customers only ever get PUBLIC_FIELDS (store.py).
"""

from __future__ import annotations

import re
import secrets
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from bson.decimal128 import Decimal128
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from cimh_common.auth import Principal
from cimh_common.errors import ProblemError, conflict, forbidden, not_found
from cimh_common.outbox import new_event
from cimh_common.paging import clamp_limit, decode_cursor, encode_cursor, page

from .store import PUBLIC_FIELDS, PUBLIC_FILTER, Store, now

PRODUCT_TYPES = ("MET", "RAD", "EQUIP", "SUPP", "MISC", "PRO")
EVENT_FIELDS = ("name", "type", "sellable", "probono", "probonoMaxPerRequest", "active", "threshold")
STAFF_FIELDS = ("sellable", "active", "threshold", "sn", "sn1", "keywords", "number", "stockCount", "version")
EDITABLE = (
    "name",
    "description",
    "details",
    "make",
    "modelname",
    "modelnumber",
    "type",
    "department",
    "project",
    "sellable",
    "probono",
    "probonoMaxPerRequest",
    "cost",
    "threshold",
    "unitquantity",
    "weight",
    "dimension",
    "sn",
    "sn1",
    "keywords",
)
DEFAULT_SETTINGS = {
    "quoteValidityDays": 30,
    "quoteReminderDays": 3,
    "approvalReminderHours": 48,
    "purgeAfterDays": 90,
    "cartInactivityDays": 180,
}
EMAIL_LISTS = ("registration", "order", "invoice", "cancellation", "lowStock")

# accountId -> {"id","email","firstname","lastname","role","status"} or None (identity /internal/accounts).
AccountLookup = Callable[[str], Awaitable[dict[str, Any] | None]]


# ---------------------------------------------------------------- helpers


def iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return str(value.astimezone(UTC).isoformat().replace("+00:00", "Z"))
    return str(value)


def to_money(value: str | None) -> Decimal128 | None:
    if value is None:
        return None
    try:
        return Decimal128(Decimal(value).quantize(Decimal("0.01")))
    except InvalidOperation as exc:
        raise ProblemError(422, "VALIDATION_FAILED", errors=[{"field": "cost", "message": "not an amount"}]) from exc


def money_str(value: Any) -> str | None:
    """Decimal128 (v2) or float (legacy rows before migration) -> '1250.00'."""
    if value is None:
        return None
    dec = value.to_decimal() if isinstance(value, Decimal128) else Decimal(str(value))
    return str(dec.quantize(Decimal("0.01")))


def actor_of(p: Principal) -> dict[str, Any]:
    return {"id": p.sub, "name": p.email or p.sub, "role": p.role}


def _image(img: Any) -> dict[str, Any] | None:
    if isinstance(img, dict) and img.get("fileId"):
        out = {k: img.get(k) for k in ("fileId", "url", "w", "h")}
        out["primary"] = bool(img.get("primary"))
        return {k: v for k, v in out.items() if v is not None or k in ("fileId", "url", "primary")}
    return None  # legacy string names are converted by the migration (M0x), never shown raw


def public_view(doc: dict[str, Any]) -> dict[str, Any]:
    out = {f: doc.get(f) for f in PUBLIC_FIELDS}
    out["probono"] = bool(doc.get("probono"))
    out["inStock"] = bool(doc.get("inStock"))
    out["images"] = [i for i in (_image(x) for x in doc.get("images") or []) if i]
    out["department"] = doc.get("department") or ""
    return out


def staff_view(doc: dict[str, Any]) -> dict[str, Any]:
    out = public_view(doc)
    out.update({f: doc.get(f) for f in STAFF_FIELDS})
    out["sellable"] = bool(doc.get("sellable"))
    out["active"] = bool(doc.get("active", True))
    out["threshold"] = int(doc.get("threshold") or 0)
    out["keywords"] = list(doc.get("keywords") or [])
    out["version"] = int(doc.get("version", 1))
    out["cost"] = money_str(doc.get("cost"))
    out["createdAt"] = iso(doc.get("createdAt"))
    out["updatedAt"] = iso(doc.get("updatedAt"))
    return out


def _keywords(values: list[str] | None) -> list[str]:
    seen: list[str] = []
    for v in values or []:
        k = v.strip().lower()
        if k and k not in seen:
            seen.append(k)
    return seen


def _event_payload(doc: dict[str, Any], changed: list[str] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"productId": doc["id"], **{f: doc.get(f) for f in EVENT_FIELDS}}
    payload["active"] = bool(doc.get("active", True))
    payload["threshold"] = int(doc.get("threshold") or 0)
    if changed is not None:
        payload["changed"] = changed
    return payload


def _audit(p: Principal, action: str, entity_type: str, entity_id: str, cid: str, **extra: Any) -> dict[str, Any]:
    payload = {"action": action, "entity": {"type": entity_type, "id": entity_id}, "actor": actor_of(p), **extra}
    return new_event("audit.recorded", payload, correlation_id=cid, actor_id=p.sub).model_dump(mode="python")


def _offset_cursor(cursor: str | None) -> int:
    if not cursor:
        return 0
    value, kind = decode_cursor(cursor)
    if kind != "offset" or not isinstance(value, int) or value < 0:
        raise ProblemError(422, "VALIDATION_FAILED", "invalid cursor")
    return value


class CatalogService:
    def __init__(self, store: Store, lookup_account: AccountLookup | None = None) -> None:
        self.store = store
        self.lookup_account = lookup_account

    # ------------------------------------------------------------------ products: read (C1-C3)

    async def list_products(
        self, p: Principal | None, filters: dict[str, Any], cursor: str | None, limit: int | None
    ) -> tuple[list[dict[str, Any]], str | None]:
        staff = bool(p and p.is_staff)
        q: dict[str, Any] = {} if staff else dict(PUBLIC_FILTER)
        if staff and not filters.get("includeInactive"):
            q["active"] = True
        if staff and filters.get("sellable") is not None:
            q["sellable"] = filters["sellable"]
        for key in ("type", "department", "project"):
            if filters.get(key):
                q[key] = filters[key]
        for key in ("probono", "inStock"):
            if filters.get(key) is not None:
                q[key] = filters[key] if filters[key] else {"$ne": True}
        docs, nxt = await page(self.store.product, q, sort_field="name", cursor=cursor, limit=limit)
        view = staff_view if staff else public_view
        return [view(d) for d in docs], nxt

    async def get_product(self, p: Principal | None, product_id: str) -> dict[str, Any]:
        staff = bool(p and p.is_staff)
        q: dict[str, Any] = {"id": product_id} if staff else {"id": product_id, **PUBLIC_FILTER}
        doc = await self.store.product.find_one(q)
        if doc is None:
            raise not_found("Product not found")
        return staff_view(doc) if staff else public_view(doc)

    async def search(
        self, p: Principal | None, text: str, filters: dict[str, Any], cursor: str | None, limit: int | None
    ) -> tuple[list[dict[str, Any]], str | None]:
        """Ranked full-text search; staff also match serial/model-number prefixes (shown first on page 1)."""
        staff = bool(p and p.is_staff)
        n = clamp_limit(limit)
        offset = _offset_cursor(cursor)
        base: dict[str, Any] = {"active": True} if staff else dict(PUBLIC_FILTER)
        for key in ("type", "department"):
            if filters.get(key):
                base[key] = filters[key]
        if filters.get("probono") is not None:
            base["probono"] = filters["probono"] if filters["probono"] else {"$ne": True}

        found: list[dict[str, Any]] = []
        if staff and offset == 0:
            rx = {"$regex": "^" + re.escape(text.strip())}
            serial = {"$or": [{"sn": rx}, {"sn1": rx}, {"modelnumber": rx}, {"id": text.strip()}]}
            found = await self.store.product.find({**base, **serial}).limit(n).to_list()
        seen = {d["id"] for d in found}
        cur = (
            self.store.product.find({**base, "$text": {"$search": text}}, {"score": {"$meta": "textScore"}})
            .sort([("score", {"$meta": "textScore"}), ("id", 1)])
            .skip(offset)
            .limit(n + 1)
        )
        ranked = await cur.to_list()
        nxt = encode_cursor(offset + n, "offset") if len(ranked) > n else None
        found += [d for d in ranked[:n] if d["id"] not in seen]
        view = staff_view if staff else public_view
        return [view(d) for d in found], nxt

    # ------------------------------------------------------------------ products: write (C4, C5)

    async def _check_reference(self, doc: dict[str, Any]) -> None:
        errors = []
        if doc.get("type") not in PRODUCT_TYPES:
            errors.append({"field": "type", "message": "unknown type"})
        departments = await self._departments()
        if departments and doc.get("department") not in departments:
            errors.append({"field": "department", "message": "not in the department list"})
        project = doc.get("project")
        if project and not await self.store.misc.find_one({"id": f"project:{project}"}):
            errors.append({"field": "project", "message": "unknown project"})
        if doc.get("probono") and not doc.get("sellable"):
            errors.append({"field": "sellable", "message": "a Pro Bono item must be sellable"})
        if doc.get("probonoMaxPerRequest") is not None and not doc.get("probono"):
            errors.append({"field": "probonoMaxPerRequest", "message": "only for Pro Bono items"})
        if errors:
            raise ProblemError(422, "VALIDATION_FAILED", errors=errors)

    async def _next_number(self) -> int:
        doc = await self.store.misc.find_one_and_update(
            {"id": "counter:product"},
            {"$inc": {"value": 1}, "$set": {"kind": "counter", "updatedAt": now()}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return int(doc["value"])

    async def create_product(self, p: Principal, body: dict[str, Any], cid: str) -> dict[str, Any]:
        fields = {k: body.get(k) for k in EDITABLE if k in body}
        fields["keywords"] = _keywords(body.get("keywords"))
        if fields.get("project"):
            fields["project"] = str(fields["project"]).lower()
        await self._check_reference(fields)
        pid = body.get("id") or f"{fields['type']}{secrets.token_hex(16)}"
        if await self.store.product.find_one({"id": pid}, {"_id": 1}):
            raise conflict("PRODUCT_EXISTS", f"A product with id {pid} already exists")
        t = now()
        doc: dict[str, Any] = {
            **fields,
            "id": pid,
            "number": await self._next_number(),
            "cost": to_money(fields.get("cost")),
            "images": [],
            "inStock": False,
            "stockCount": None,
            "active": True,
            "version": 1,
            "createdAt": t,
            "updatedAt": t,
            "createdBy": actor_of(p),
        }
        evt = new_event("product.created", _event_payload(doc), correlation_id=cid, actor_id=p.sub)
        doc["outbox"] = [evt.model_dump(mode="python")]
        try:
            await self.store.product.insert_one(doc)
        except DuplicateKeyError as exc:
            raise conflict("PRODUCT_EXISTS", f"A product with id {pid} already exists") from exc
        return staff_view(doc)

    async def update_product(
        self, p: Principal, product_id: str, version: int, body: dict[str, Any], cid: str
    ) -> dict[str, Any]:
        current = await self.store.product.find_one({"id": product_id})
        if current is None:
            raise not_found("Product not found")
        fields = {k: body[k] for k in EDITABLE if k in body}
        if "keywords" in fields:
            fields["keywords"] = _keywords(fields["keywords"])
        if fields.get("project"):
            fields["project"] = str(fields["project"]).lower()
        if "cost" in fields:
            fields["cost"] = to_money(fields["cost"])
        merged = {**current, **fields}
        if merged.get("probono") is False and "probonoMaxPerRequest" not in body:
            merged["probonoMaxPerRequest"] = fields["probonoMaxPerRequest"] = None
        await self._check_reference(merged)
        changed = sorted(k for k, v in fields.items() if current.get(k) != v)
        if current.get("version", 1) != version:
            raise conflict("VERSION_CONFLICT", "The product was changed by someone else; reload and retry")
        if not changed:
            return staff_view(current)
        evt = new_event(
            "product.updated", _event_payload(merged, changed), correlation_id=cid, actor_id=p.sub
        ).model_dump(mode="python")
        update: dict[str, Any] = {
            "$set": {**{k: fields[k] for k in changed}, "updatedAt": now(), "updatedBy": actor_of(p)},
            "$inc": {"version": 1},
            "$push": {"outbox": evt},
        }
        if "cost" in changed:
            # Cost is commercial data: admins see who changed it in the audit log.
            audit = _audit(
                p,
                "product.cost_changed",
                "product",
                product_id,
                cid,
                **{"from": money_str(current.get("cost")), "to": money_str(fields["cost"])},
            )
            update["$push"] = {"outbox": {"$each": [evt, audit]}}
        doc = await self.store.product.find_one_and_update(
            {"id": product_id, "version": version}, update, return_document=ReturnDocument.AFTER
        )
        if doc is None:
            raise conflict("VERSION_CONFLICT", "The product was changed by someone else; reload and retry")
        return staff_view(doc)

    async def deactivate_product(self, p: Principal, product_id: str, version: int, cid: str) -> None:
        current = await self.store.product.find_one({"id": product_id})
        if current is None:
            raise not_found("Product not found")
        if not current.get("active", True):
            return
        events = [
            new_event("product.deleted", {"productId": product_id}, correlation_id=cid, actor_id=p.sub).model_dump(
                mode="python"
            ),
            _audit(p, "product.deactivated", "product", product_id, cid),
        ]
        doc = await self.store.product.find_one_and_update(
            {"id": product_id, "version": version},
            {
                "$set": {"active": False, "updatedAt": now(), "updatedBy": actor_of(p)},
                "$inc": {"version": 1},
                "$push": {"outbox": {"$each": events}},
            },
        )
        if doc is None:
            raise conflict("VERSION_CONFLICT", "The product was changed by someone else; reload and retry")

    # ------------------------------------------------------------------ images (C6)

    async def queue_images(
        self, p: Principal, product_id: str, sources: list[str], remove_background: bool, cid: str
    ) -> list[str]:
        """`sources` are paths relative to MEDIA_ROOT, already written by the API layer."""
        job_ids = [f"JOB{secrets.token_hex(12).upper()}" for _ in sources]
        events = [
            new_event(
                "image.process",
                {"jobId": jid, "productId": product_id, "sourcePath": src, "removeBackground": remove_background},
                correlation_id=cid,
                actor_id=p.sub,
            ).model_dump(mode="python")
            for jid, src in zip(job_ids, sources, strict=True)
        ]
        res = await self.store.product.update_one(
            {"id": product_id}, {"$push": {"outbox": {"$each": events}}, "$set": {"updatedAt": now()}}
        )
        if not res.matched_count:
            raise not_found("Product not found")
        return job_ids

    async def image_processed(self, payload: dict[str, Any], cid: str) -> bool:
        """media.results consumer: attach the processed image. Idempotent per fileId."""
        if not payload.get("ok"):
            return False
        pid, fid = payload["productId"], payload["fileId"]
        current = await self.store.product.find_one({"id": pid}, {"images": 1})
        if current is None:
            return False
        images = [i for i in (current.get("images") or []) if isinstance(i, dict)]
        if any(i.get("fileId") == fid for i in images):
            return False
        image = {
            "fileId": fid,
            "url": payload["url"],
            "w": payload.get("w"),
            "h": payload.get("h"),
            "primary": not any(i.get("primary") for i in images),
        }
        evt = new_event(
            "product.image_added", {"productId": pid, "fileId": fid, "url": payload["url"]}, correlation_id=cid
        ).model_dump(mode="python")
        res = await self.store.product.update_one(
            {"id": pid, "images.fileId": {"$ne": fid}},
            {"$push": {"images": image, "outbox": evt}, "$set": {"updatedAt": now()}, "$inc": {"version": 1}},
        )
        return bool(res.modified_count)

    async def set_primary_image(self, p: Principal, product_id: str, file_id: str, cid: str) -> dict[str, Any]:
        doc = await self.store.product.find_one({"id": product_id})
        if doc is None:
            raise not_found("Product not found")
        images = [i for i in (doc.get("images") or []) if isinstance(i, dict)]
        if not any(i.get("fileId") == file_id for i in images):
            raise not_found("Image not found")
        images = [{**i, "primary": i.get("fileId") == file_id} for i in images]
        return await self._save_images(p, doc, images, cid)

    async def remove_image(self, p: Principal, product_id: str, file_id: str, cid: str) -> str | None:
        """Returns the removed image's URL (the API deletes the file) or raises 404."""
        doc = await self.store.product.find_one({"id": product_id})
        if doc is None:
            raise not_found("Product not found")
        images = [i for i in (doc.get("images") or []) if isinstance(i, dict)]
        gone = next((i for i in images if i.get("fileId") == file_id), None)
        if gone is None:
            raise not_found("Image not found")
        rest = [i for i in images if i.get("fileId") != file_id]
        if rest and not any(i.get("primary") for i in rest):
            rest[0] = {**rest[0], "primary": True}
        await self._save_images(p, doc, rest, cid)
        return str(gone.get("url") or "")

    async def _save_images(
        self, p: Principal, doc: dict[str, Any], images: list[dict[str, Any]], cid: str
    ) -> dict[str, Any]:
        evt = new_event(
            "product.updated", _event_payload(doc, ["images"]), correlation_id=cid, actor_id=p.sub
        ).model_dump(mode="python")
        saved = await self.store.product.find_one_and_update(
            {"id": doc["id"], "version": doc.get("version", 1)},
            {
                "$set": {"images": images, "updatedAt": now(), "updatedBy": actor_of(p)},
                "$inc": {"version": 1},
                "$push": {"outbox": evt},
            },
            return_document=ReturnDocument.AFTER,
        )
        if saved is None:
            raise conflict("VERSION_CONFLICT", "The product was changed by someone else; reload and retry")
        return staff_view(saved)

    # ------------------------------------------------------------------ stock (inventory.stock.events)

    async def stock_changed(self, payload: dict[str, Any], occurred_at: datetime) -> bool:
        """`inStock` / `stockCount` are display-only copies; an older event never overwrites a newer one."""
        available = int(payload["available"])
        res = await self.store.product.update_one(
            {
                "id": payload["productId"],
                "$or": [{"stockAt": {"$exists": False}}, {"stockAt": {"$lte": occurred_at}}],
            },
            {"$set": {"inStock": available > 0, "stockCount": available, "stockAt": occurred_at}},
        )
        return bool(res.modified_count)

    # ------------------------------------------------------------------ reference data (C8)

    async def _departments(self) -> list[str]:
        doc = await self.store.misc.find_one({"id": "departments"})
        return list(doc.get("values") or []) if doc else []

    async def reference(self, include_inactive: bool = False) -> dict[str, Any]:
        types_doc = await self.store.misc.find_one({"id": "types"})
        labels = {t["key"]: t["label"] for t in (types_doc or {}).get("values", []) if isinstance(t, dict)}
        q: dict[str, Any] = {"kind": "projects"} if include_inactive else {"kind": "projects", "active": True}
        projects = await self.store.misc.find(q).to_list()
        return {
            "departments": await self._departments(),
            "types": [{"key": k, "label": labels.get(k, k)} for k in PRODUCT_TYPES],
            "projects": sorted(
                ({"code": d["code"], "name": d["name"], "active": bool(d.get("active", True))} for d in projects),
                key=lambda x: x["name"],
            ),
        }

    async def _save_misc(self, p: Principal, doc_id: str, kind: str, fields: dict[str, Any], cid: str) -> None:
        audit = _audit(p, f"settings.{kind}_changed", "settings", doc_id, cid)
        await self.store.misc.update_one(
            {"id": doc_id},
            {
                "$set": {**fields, "kind": kind, "updatedAt": now(), "updatedBy": actor_of(p)},
                "$push": {"outbox": audit},
            },
            upsert=True,
        )

    async def put_departments(self, p: Principal, values: list[str], cid: str) -> None:
        clean: list[str] = []
        for v in values:
            v = v.strip()
            if not v or len(v) > 100:
                raise ProblemError(422, "VALIDATION_FAILED", errors=[{"field": "values", "message": "1..100 chars"}])
            if v not in clean:
                clean.append(v)
        await self._save_misc(p, "departments", "departments", {"values": clean}, cid)

    async def create_project(self, p: Principal, body: dict[str, Any], cid: str) -> dict[str, Any]:
        code = body["code"].strip().lower()
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,49}", code):
            raise ProblemError(422, "VALIDATION_FAILED", errors=[{"field": "code", "message": "letters, digits, - _"}])
        doc = {
            "id": f"project:{code}",
            "kind": "projects",
            "code": code,
            "name": body["name"].strip(),
            "active": bool(body.get("active", True)),
            "updatedAt": now(),
            "updatedBy": actor_of(p),
            "outbox": [_audit(p, "project.created", "project", code, cid)],
        }
        try:
            await self.store.misc.insert_one(doc)
        except DuplicateKeyError as exc:
            raise conflict("PROJECT_EXISTS", f"Project {code} already exists") from exc
        return {"code": code, "name": doc["name"], "active": doc["active"]}

    async def update_project(self, p: Principal, code: str, body: dict[str, Any], cid: str) -> dict[str, Any]:
        fields = {k: body[k] for k in ("name", "active") if body.get(k) is not None}
        doc = await self.store.misc.find_one_and_update(
            {"id": f"project:{code.lower()}"},
            {
                "$set": {**fields, "updatedAt": now(), "updatedBy": actor_of(p)},
                "$push": {"outbox": _audit(p, "project.updated", "project", code.lower(), cid, to=fields)},
            },
            return_document=ReturnDocument.AFTER,
        )
        if doc is None:
            raise not_found("Project not found")
        return {"code": doc["code"], "name": doc["name"], "active": bool(doc["active"])}

    # ------------------------------------------------------------------ settings (C8)

    async def fees(self) -> dict[str, Any]:
        doc = await self.store.misc.find_one({"id": "fees"})
        types = (doc or {}).get("types") or []
        return {"types": [{"name": t["name"], "fee": money_str(t["fee"])} for t in types]}

    async def put_fees(self, p: Principal, body: dict[str, Any], cid: str) -> dict[str, Any]:
        names = [t["name"] for t in body["types"]]
        if len(set(names)) != len(names):
            raise ProblemError(422, "VALIDATION_FAILED", errors=[{"field": "types", "message": "duplicate name"}])
        types = [{"name": t["name"], "fee": to_money(t["fee"])} for t in body["types"]]
        await self._save_misc(p, "fees", "fees", {"types": types}, cid)
        return await self.fees()

    async def general(self) -> dict[str, Any]:
        doc = await self.store.misc.find_one({"id": "settings"}) or {}
        return {k: doc.get(k, v) for k, v in DEFAULT_SETTINGS.items()}

    async def put_general(self, p: Principal, body: dict[str, Any], cid: str) -> dict[str, Any]:
        await self._save_misc(p, "settings", "settings", {k: body.get(k, v) for k, v in DEFAULT_SETTINGS.items()}, cid)
        return await self.general()

    async def email_lists(self) -> dict[str, Any]:
        doc = await self.store.misc.find_one({"id": "emails"}) or {}
        return {name: list(doc.get(name) or []) for name in EMAIL_LISTS}

    async def put_email_lists(self, p: Principal, body: dict[str, Any], cid: str) -> dict[str, Any]:
        if self.lookup_account is None:
            raise ProblemError(503, "DEPENDENCY_UNAVAILABLE", "Account lookup is not configured")
        cache: dict[str, dict[str, Any] | None] = {}
        out: dict[str, list[dict[str, Any]]] = {}
        errors = []
        for name in EMAIL_LISTS:
            members: list[dict[str, Any]] = []
            for i, m in enumerate(body.get(name) or []):
                aid = m["accountId"]
                if aid not in cache:
                    try:
                        cache[aid] = await self.lookup_account(aid)
                    except Exception as exc:
                        raise ProblemError(
                            503, "DEPENDENCY_UNAVAILABLE", "Accounts can't be checked right now; nothing was saved"
                        ) from exc
                acc = cache[aid]
                if not acc or acc.get("role") not in ("staff", "admin") or acc.get("status") != "ACTIVE":
                    errors.append({"field": f"{name}[{i}]", "message": "must be an active staff or admin account"})
                    continue
                if any(x["accountId"] == aid for x in members):
                    continue
                members.append(
                    {
                        "accountId": aid,
                        "email": acc["email"],
                        "firstname": acc["firstname"],
                        "lastname": acc["lastname"],
                    }
                )
            out[name] = members
        if errors:
            raise ProblemError(422, "VALIDATION_FAILED", errors=errors)
        await self._save_misc(p, "emails", "emailLists", out, cid)
        return out

    # ------------------------------------------------------------------ internal (service tokens)

    async def summaries(self, ids: list[str]) -> list[dict[str, Any]]:
        docs = await self.store.product.find({"id": {"$in": ids}}).to_list()
        return [staff_view(d) for d in docs]

    async def places(self, filters: dict[str, Any]) -> list[dict[str, Any]]:
        q: dict[str, Any] = {"kind": {"$in": ["site", "location", "shelf"]}}
        for key in ("kind", "site", "location"):
            if filters.get(key):
                q[key] = filters[key]
        docs = await self.store.misc.find(q).sort([("kind", 1), ("id", 1)]).to_list()
        return [_place(d) for d in docs]

    async def put_place(self, p: Principal, body: dict[str, Any]) -> dict[str, Any]:
        if p.sub != "svc:inventory":
            raise forbidden("Only inventory-svc may change places")
        kind = body["kind"]
        if kind in ("location", "shelf") and not body.get("site"):
            raise ProblemError(422, "VALIDATION_FAILED", errors=[{"field": "site", "message": "required"}])
        if kind == "shelf" and not body.get("location"):
            raise ProblemError(422, "VALIDATION_FAILED", errors=[{"field": "location", "message": "required"}])
        fields = {**body, "id": body["barcode"], "updatedAt": now(), "updatedBy": actor_of(p)}
        doc = await self.store.misc.find_one_and_update(
            {"id": body["barcode"]}, {"$set": fields}, upsert=True, return_document=ReturnDocument.AFTER
        )
        return _place(doc)


def _place(d: dict[str, Any]) -> dict[str, Any]:
    out = {
        k: d.get(k)
        for k in ("kind", "barcode", "name", "site", "location", "number", "country", "address", "description")
    }
    out["barcode"] = d.get("barcode") or d["id"]
    out["name"] = d.get("name") or out["barcode"]
    out["active"] = bool(d.get("active", True))
    return out
