"""Legacy SIA export (mongoexport JSON) -> v2 documents (MIGRATION_PLAN §5, M01-M07 + stock).

Usage:  python tools/migrate/legacy_to_v2.py <export-dir> <out-dir>

Reads `inventory.<collection>.json` (canonical extended JSON arrays) and writes one extended-JSON file per
target collection to <out-dir> (for `mongoimport --jsonArray`) plus `report.json`, which holds counts and
ids only (no personal data). Pure function of its input: re-running gives the same documents apart from
generated ids/timestamps. Files (M08) are handled by `files_to_v2.py`.
"""

from __future__ import annotations

import json
import re
import secrets
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

from bson import json_util
from bson.decimal128 import Decimal128

NOW = datetime.now(UTC).replace(microsecond=0)
MIGRATE = {"id": "svc:migrate", "name": "Legacy migration", "role": "system"}
REASON = "Migrated from legacy"
CIMH_DOMAIN = "@cimh.edu.bb"

COUNTRIES = {
    "barbados": "BB",
    "jamaica": "JM",
    "st lucia": "LC",
    "saint lucia": "LC",
    "dominica": "DM",
    "nevis": "KN",
    "st kitts and nevis": "KN",
    "anguilla": "AI",
    "mexico": "MX",
    "turks and caicos islands": "TC",
    "st vincent and the grenadines": "VC",
    "saint vincent and the grenadines": "VC",
    "british virgin islands": "VG",
    "tortola british virgin islands": "VG",
    "grenada": "GD",
    "haiti": "HT",
    "bahamas": "BS",
    "trinidad and tobago": "TT",
    "guyana": "GY",
    "belize": "BZ",
    "antigua and barbuda": "AG",
    "cayman islands": "KY",
    "bermuda": "BM",
    "suriname": "SR",
    "montserrat": "MS",
}
TYPE_LABELS = {
    "MET": "Met",
    "RAD": "Radar",
    "PRO": "Projects",
    "MISC": "Misc",
    "EQUIP": "Equipment",
    "SUPP": "Supplies",
}
DEFAULT_SETTINGS = {
    "quoteValidityDays": 30,
    "quoteReminderDays": 3,
    "approvalReminderHours": 48,
    "purgeAfterDays": 90,
    "cartInactivityDays": 180,
}
FILE_KINDS = {"inv": "invoice", "ci": "commercial_invoice", "payment": "upload", "file": "upload"}


def load(src: Path, name: str) -> list[dict[str, Any]]:
    docs = json_util.loads((src / f"inventory.{name}.json").read_text(encoding="utf-8"))
    for d in docs:
        d.pop("_id", None)  # fresh ObjectIds in the target
    return docs


def money(v: Any) -> Decimal128 | None:
    if v in (None, ""):
        return None
    return Decimal128(Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def utc(v: Any) -> datetime | None:
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=UTC)
    if isinstance(v, (int, float)) and v > 0:
        return datetime.fromtimestamp(v / 1000 if v > 1e11 else v, UTC)
    if isinstance(v, str) and v.strip():
        s = v.strip()
        for fmt in (
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
            "%d/%m/%Y",
            "%m/%d/%Y",
            "%d-%m-%Y",
            "%B %d, %Y",
            "%b %d, %Y",
            "%d %B %Y",
            "%a, %d %b %Y %H:%M:%S %Z",
            "%a %b %d %Y",
        ):
            try:
                return datetime.strptime(s, fmt).replace(tzinfo=UTC)
            except ValueError:
                pass
        try:
            d = datetime.fromisoformat(s.replace("Z", "+00:00"))
            return d if d.tzinfo else d.replace(tzinfo=UTC)
        except ValueError:
            return None
    return None


# Every free-text -> v2 value decision, for the DR-1 report (MIGRATION_PLAN §4 "mapping table of every free-text
# value"). Fields marked personal can hold names ("hand delivered by ..."): their source values go only to the
# git-ignored local file next to the export, never into report.json.
MAPPINGS: defaultdict[str, Counter] = defaultdict(Counter)
PERSONAL = {"shipping.method -> carrier", "organisation text -> organisation"}


def record_mapping(field: str, source: Any, target: Any) -> None:
    MAPPINGS[field][(str(source), str(target))] += 1


def mapping_tables(local: bool) -> list[dict[str, Any]]:
    out = []
    for field, counter in sorted(MAPPINGS.items()):
        rows = [{"from": a, "to": b, "count": n} for (a, b), n in sorted(counter.items())]
        if field in PERSONAL and not local:
            by_target: Counter = Counter()
            for r in rows:
                by_target[r["to"] if not r["to"].startswith("ORG") else "an organisation"] += r["count"]
            rows = [
                {"from": f"{len(counter)} distinct free-text values", "to": t, "count": n}
                for t, n in sorted(by_target.items())
            ]
        out.append({"field": field, "personal": field in PERSONAL, "rows": rows})
    return out


def fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    s = s.lower().replace("&", " and ").replace("st.", "st ")
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def country(s: str, report: Counter) -> str | None:
    if not (s or "").strip():
        return None
    k = fold(s)
    if k in COUNTRIES:
        record_mapping("country text -> ISO code", s.strip(), COUNTRIES[k])
        return COUNTRIES[k]
    if k.endswith("xico"):  # "México" exported with a broken accent
        record_mapping("country text -> ISO code", s.strip(), "MX")
        return "MX"
    report[s.strip()] += 1
    record_mapping("country text -> ISO code", s.strip(), "UNMAPPED (review)")
    return None


def status_change(to: str, at: datetime) -> dict[str, Any]:
    return {"from": None, "to": to, "by": MIGRATE, "at": at, "reason": REASON}


# ---------------------------------------------------------------------------------------------- M01 misc
def m01_misc(
    misc: list[dict[str, Any]], products: list[dict[str, Any]], accounts_by_id: dict[str, Any], rep: dict[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    out: list[dict[str, Any]] = []
    project_codes: dict[str, str] = {}
    for m in misc:
        kind = m["id"]
        if kind == "departments":
            out.append(
                {
                    "id": "departments",
                    "kind": "departments",
                    "values": [v.strip() for v in m["departments"] if v.strip()],
                    "updatedAt": NOW,
                }
            )
        elif kind == "types" and isinstance(m.get("types"), dict):
            codes = list(dict.fromkeys(m["types"].values()))
            out.append(
                {
                    "id": "types",
                    "kind": "types",
                    "updatedAt": NOW,
                    "values": [{"key": c, "label": TYPE_LABELS.get(c, c)} for c in codes],
                }
            )
        elif kind == "fees":
            out.append(
                {
                    "id": "fees",
                    "kind": "fees",
                    "updatedAt": NOW,
                    "types": [{"name": t["name"], "fee": money(t["fee"])} for t in m["types"]],
                }
            )
        elif kind == "project":
            code = re.sub(r"[^a-z0-9_-]+", "-", m["name"].strip().lower()).strip("-")
            project_codes[m["name"].strip().lower()] = code
            out.append(
                {
                    "id": f"project:{code}",
                    "kind": "projects",
                    "code": code,
                    "name": m["name"].strip(),
                    "description": m.get("description", ""),
                    "barcode": m.get("barcode"),
                    "active": True,
                    "updatedAt": NOW,
                }
            )
        elif kind == "emails":
            doc: dict[str, Any] = {"id": "emails", "kind": "emailLists", "updatedAt": NOW, "lowStock": []}
            for name in ("registration", "order", "invoice", "cancellation"):
                members = []
                for x in m.get(name) or []:
                    acc = accounts_by_id.get(x.get("account"))
                    if not acc or acc["role"] not in ("staff", "admin"):
                        rep["warnings"].append(f"emailLists.{name}: dropped member {x.get('account')} (not staff)")
                        continue
                    members.append(
                        {
                            "accountId": acc["id"],
                            "email": acc["email"],
                            "firstname": acc["firstname"],
                            "lastname": acc["lastname"],
                        }
                    )
                doc[name] = members
            out.append(doc)
        elif kind == "site":
            out.append(
                {
                    "id": m["barcode"],
                    "kind": "site",
                    "barcode": m["barcode"],
                    "name": m["name"],
                    "country": m.get("country", ""),
                    "address": m.get("address", ""),
                    "active": True,
                    "updatedAt": NOW,
                }
            )
        elif kind == "location":
            out.append(
                {
                    "id": m["barcode"],
                    "kind": "location",
                    "barcode": m["barcode"],
                    "name": m["name"],
                    "site": m["site"],
                    "active": True,
                    "updatedAt": NOW,
                }
            )
            for sh in m.get("shelves") or []:
                out.append(
                    {
                        "id": sh["barcode"],
                        "kind": "shelf",
                        "barcode": sh["barcode"],
                        "number": int(sh["number"]),
                        "site": m["site"],
                        "location": m["barcode"],
                        "active": True,
                        "updatedAt": NOW,
                    }
                )
        else:
            rep["warnings"].append(f"misc: unknown legacy doc id {kind!r} skipped")
    out.append({"id": "settings", "kind": "settings", **DEFAULT_SETTINGS, "updatedAt": NOW})
    out.append(
        {
            "id": "counter:product",
            "kind": "counter",
            "value": max((int(p.get("number") or 0) for p in products), default=0),
            "updatedAt": NOW,
        }
    )
    rep["counts"]["misc"] = Counter(d["kind"] for d in out)
    return out, project_codes


# ---------------------------------------------------------------------------------- M02 organisations + accounts
def m02_accounts(
    accounts: list[dict[str, Any]], orders: list[dict[str, Any]], rep: dict[str, Any], unknown_countries: Counter
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    orgs: dict[str, dict[str, Any]] = {}

    def org_for(name: str, iso: str | None) -> dict[str, Any] | None:
        clean = re.sub(r"\s+", " ", (name or "").strip())
        if not clean:
            return None
        key = clean.lower()
        org = orgs.get(key)
        if org is None:
            org = {
                "id": "ORG" + secrets.token_hex(13).upper(),
                "name": clean,
                "nameKey": key,
                "country": iso or "BB",
                "type": None,
                "emailDomains": [],
                "aliases": [],
                "active": True,
                "mergedInto": None,
                "createdBy": MIGRATE,
                "createdAt": NOW,
                "updatedAt": NOW,
                "version": 1,
            }
            if not iso:
                rep["review"].append(f"organisation {org['id']}: country unknown, set to BB")
            orgs[key] = org
        record_mapping("organisation text -> organisation", clean, org["id"])
        return org

    cimh = org_for("CIMH", "BB")
    assert cimh is not None
    cimh["emailDomains"] = ["cimh.edu.bb"]
    cimh["type"] = "met_service"

    # The account's organisation = the one on its most recent order (legacy accounts had no org field).
    latest: dict[str, dict[str, Any]] = {}
    for o in sorted(orders, key=lambda o: utc(o.get("ordered")) or NOW):
        for part in ("shipto", "billedto"):
            org_for(o[part].get("organization", ""), country(o[part].get("country", ""), unknown_countries))
        latest[o["customer"]] = o

    # Legacy allowed the same email more than once (double-submitted registrations). Keep the oldest account
    # per email, or the one with orders; the others are listed for review.
    active_ids = {o["customer"] for o in orders}
    keep: dict[str, dict[str, Any]] = {}
    for a in sorted(accounts, key=lambda a: (a["id"] not in active_ids, a.get("timestamp") or 0)):
        email = a["email"].strip().lower()
        if email in keep:
            rep["review"].append(f"account {a['id']}: duplicate email of {keep[email]['id']}, not migrated")
            continue
        keep[email] = a
    kept_ids = {a["id"] for a in keep.values()}

    out = []
    for a in accounts:
        if a["id"] not in kept_ids:
            continue
        email = a["email"].strip().lower()
        is_cimh = email.endswith(CIMH_DOMAIN)
        created = utc(a.get("timestamp")) or utc(a.get("registered")) or NOW
        verified = utc(a.get("registered")) or created
        org_id, org_text, acc_country = None, None, None
        if is_cimh:
            org_id, acc_country = cimh["id"], "BB"
        elif a["id"] in latest:
            st = latest[a["id"]]["shipto"]
            org_text = (st.get("organization") or "").strip() or None
            acc_country = country(st.get("country", ""), Counter())
            org = org_for(org_text or "", acc_country) if org_text else None
            org_id = org["id"] if org else None
        if not is_cimh and org_id is None:
            rep["review"].append(f"account {a['id']}: no organisation (no orders); admin to assign")
        doc: dict[str, Any] = {
            "id": a["id"],
            "email": email,
            "passwordHash": "",
            "legacyPasswordHash": a["password"],
            "firstname": a["firstname"].strip(),
            "lastname": a["lastname"].strip(),
            "phone": None,
            "role": a["role"] if a["role"] in ("user", "staff", "admin") else "user",
            "status": "ACTIVE",
            "isCimh": is_cimh,
            "organisationText": org_text,
            "organisationId": org_id,
            "department": a.get("department") or None,
            "country": acc_country,
            "addresses": [],
            "image": None if a.get("image") in (None, "", "default.png") else a["image"],
            "verifiedAt": verified,
            "approvedAt": verified,
            "approvedBy": MIGRATE,
            "statusHistory": [status_change("ACTIVE", NOW)],
            "failedLogins": {"count": 0, "lockouts": 0},
            "mfa": {"enabled": False},
            "createdAt": created,
            "updatedAt": NOW,
            "version": 1,
            "outbox": [],
        }
        if a["role"] in ("staff", "admin") and a.get("shelf"):
            doc["defaults"] = {"site": a.get("site", ""), "location": a.get("location", ""), "shelf": a["shelf"]}
        if a.get("address"):
            rep["warnings"].append(f"account {a['id']}: {len(a['address'])} free-text addresses not migrated")
        out.append(doc)
    rep["counts"]["accounts"] = Counter(f"{d['role']}{'/cimh' if d['isCimh'] else ''}" for d in out)
    rep["counts"]["organisations"] = len(orgs)
    rep["counts"]["accounts_without_org"] = sum(1 for d in out if not d["isCimh"] and not d["organisationId"])
    return out, list(orgs.values())


# ------------------------------------------------------------------------------------------- M03 product
def m03_products(
    products: list[dict[str, Any]], project_codes: dict[str, str], rep: dict[str, Any]
) -> list[dict[str, Any]]:
    out = []
    for p in products:
        sellable = str(p.get("sellable", "")).lower()
        record_mapping(
            "product.sellable",
            sellable or "(empty)",
            "probono" if sellable == "probono" else str(sellable in ("yes", "probono")).lower(),
        )
        project = (p.get("project") or "").strip().lower()
        if project and project not in project_codes:
            rep["warnings"].append(f"product {p['id']}: unknown project {project!r} cleared")
        doc = {
            "id": p["id"],
            "number": int(p.get("number") or 0),
            "name": p["name"].strip(),
            "description": p.get("description", ""),
            "details": p.get("details", ""),
            "make": p.get("make", ""),
            "modelname": p.get("modelname", ""),
            "modelnumber": p.get("modelnumber", ""),
            "type": p["type"],
            "department": p.get("department", ""),
            "project": project_codes.get(project, "") if project else "",
            "sellable": sellable in ("yes", "probono"),
            "probono": sellable == "probono",
            "probonoMaxPerRequest": None,
            "cost": money(p.get("cost") or 0),
            "threshold": int(p.get("threshold") or 0),
            "unitquantity": int(p.get("unitquantity") or 1),
            "weight": p.get("weight"),
            "dimension": p.get("dimension", ""),
            "sn": p.get("sn", ""),
            "sn1": p.get("sn1", ""),
            "keywords": list(dict.fromkeys(k.strip().lower() for k in p.get("keywords") or [] if k.strip())),
            "images": [],
            "legacyImages": list(p.get("images") or []),  # attached by files_to_v2.py (M08)
            "inStock": False,
            "stockCount": 0,
            "active": True,
            "version": 1,
            "createdAt": NOW,
            "updatedAt": NOW,
            "createdBy": MIGRATE,
            "outbox": [],
        }
        if sellable not in ("yes", "no", "probono"):
            rep["warnings"].append(f"product {p['id']}: sellable {sellable!r} -> false")
        out.append(doc)
    rep["counts"]["product"] = Counter(
        ("probono" if d["probono"] else "sellable" if d["sellable"] else "internal") for d in out
    )
    return out


# --------------------------------------------------------------------------- M04 storage + stock, M05 history
def m04_storage(
    storage: list[dict[str, Any]], products: list[dict[str, Any]], rep: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    pids = {p["id"] for p in products}
    seen: set[str] = set()
    units = []
    for s in storage:
        if s["barcode"] in seen:
            rep["warnings"].append(f"storage: duplicate barcode {s['barcode']} skipped")
            continue
        seen.add(s["barcode"])
        if s["product"] not in pids:
            rep["warnings"].append(f"storage {s['barcode']}: unknown product {s['product']}")
        u = dict(s)
        u["stowdate"], u["pickeddate"] = utc(s.get("stowdate")), utc(s.get("pickeddate"))
        u["createdAt"] = u["stowdate"] or NOW
        u["updatedAt"] = NOW
        units.append(u)
    by_product: dict[str, Counter] = defaultdict(Counter)
    for u in units:
        c = by_product[u["product"]]
        if u.get("stowed") and not u.get("picked"):
            c["available"] += 1
        if u.get("picked"):
            c["picked"] += 1
    stock = []
    for p in products:
        c = by_product[p["id"]]
        threshold, active = p["threshold"], p["active"]
        available = c["available"]
        stock.append(
            {
                "id": p["id"],
                "productName": p["name"],
                "type": p["type"],
                "threshold": threshold,
                "active": active,
                "available": available,
                "reserved": 0,
                "picked": c["picked"],
                "assigned": 0,
                "low": active and threshold > 0 and available <= threshold,
                "updatedAt": NOW,
                "outbox": [],
            }
        )
        p["inStock"], p["stockCount"], p["stockAt"] = available > 0, available, NOW
    rep["counts"]["storage"] = Counter(
        "available" if u.get("stowed") and not u.get("picked") else "picked" if u.get("picked") else "other"
        for u in units
    )
    rep["counts"]["stock_low"] = sum(1 for s in stock if s["low"])
    return units, stock


def m05_history(
    history: list[dict[str, Any]], units: list[dict[str, Any]], rep: dict[str, Any]
) -> list[dict[str, Any]]:
    order_of = {u["barcode"]: u.get("orderid") or None for u in units}
    out = []
    for h in history:
        op = h.get("operation")
        row = {k: h.get(k, "") for k in ("id", "user", "site", "location", "shelf", "reason")}
        row["date"] = utc(h.get("date")) or NOW
        row["accountId"] = h.get("user") or None
        if op == "orderpick":
            row["operation"], row["orderId"] = "pick", order_of.get(h["id"])
            if not row["orderId"]:
                rep["warnings"].append(f"history orderpick {h['id']}: no order found")
        elif op in ("stow", "pick"):
            row["operation"] = op
        else:
            row["operation"] = "adjust"
            rep["warnings"].append(f"history: unknown operation {op!r} -> adjust")
        out.append(row)
    rep["counts"]["history"] = Counter(r["operation"] for r in out)
    return out


# ---------------------------------------------------------------------------------- M06 carts, M07 orders
def snapshot(p: dict[str, Any] | None) -> dict[str, Any]:
    p = p or {}
    return {k: p.get(k, "") for k in ("name", "make", "modelname", "modelnumber", "type")} | {
        "probono": bool(p.get("probono"))
    }


def m06_carts(
    accounts: list[dict[str, Any]], products_by_id: dict[str, Any], rep: dict[str, Any]
) -> list[dict[str, Any]]:
    out = []
    for a in accounts:
        if a["email"].lower().endswith(CIMH_DOMAIN):
            continue  # CIMH accounts get no cart
        lines = []
        for i, item in enumerate(a.get("cart") or []):
            p = products_by_id.get(item.get("id"))
            if not p or not p["sellable"]:
                rep["warnings"].append(f"cart of {a['id']}: product {item.get('id')} dropped (unknown/not sellable)")
                continue
            lines.append(
                {
                    "lineId": f"L{i + 1}",
                    "productId": p["id"],
                    "product": snapshot(p),
                    "qty": max(1, int(item.get("count") or 1)),
                }
            )
        if lines:
            out.append(
                {
                    "id": "CRT" + secrets.token_hex(16),
                    "type": None,
                    "status": "CART",
                    "customer": a["id"],
                    "lines": lines,
                    "currency": None,
                    "createdAt": NOW,
                    "updatedAt": NOW,
                    "version": 1,
                    "history": [],
                    "outbox": [],
                }
            )
    rep["counts"]["carts"] = len(out)
    return out


def contact(src: dict[str, Any], unknown: Counter) -> dict[str, Any]:
    return {
        "firstname": src.get("firstname", ""),
        "lastname": src.get("lastname", ""),
        "email": (src.get("email") or "").strip().lower(),
        "tel": src.get("tel", ""),
        "line1": src.get("address", ""),
        "line2": None,
        "city": src.get("city", ""),
        "parish": src.get("parish") or None,
        "country": country(src.get("country", ""), unknown) or "",
        "zip": src.get("zip") or None,
        "organisation": (src.get("organization") or "").strip() or None,
        "attention": src.get("office") or None,
    }


def m07_orders(
    orders: list[dict[str, Any]],
    accounts_v2: dict[str, Any],
    products_by_id: dict[str, Any],
    rep: dict[str, Any],
    unknown: Counter,
) -> list[dict[str, Any]]:
    out = []
    for o in orders:
        acc = accounts_v2.get(o["customer"])
        if acc is None:
            rep["warnings"].append(f"order {o['id']}: unknown customer {o['customer']}")
        status = "DELIVERED" if o.get("complete") else "CANCELLED" if o.get("cancelled") else "SUBMITTED"
        record_mapping(
            "order state -> status",
            "complete" if o.get("complete") else "cancelled" if o.get("cancelled") else "open",
            status,
        )
        submitted = utc(o.get("ordered")) or NOW
        sh = o.get("shipping") or {}
        method = (sh.get("method") or "").strip()
        shipping = None
        if method:
            m = method.lower()
            carrier = "FEDEX" if m == "fedex" else "DHL" if m == "dhl" else "HAND"
            record_mapping("shipping.method -> carrier", method, carrier)
            sdate = utc(sh.get("date"))
            if sh.get("date") and sdate is None:
                rep["warnings"].append(f"order {o['id']}: shipping date unparseable")
            shipping = {
                "carrier": carrier,
                "tracking": sh.get("tracking") or None,
                "note": method if carrier == "HAND" else None,
                "cost": money(sh.get("cost")),
                "date": sdate or submitted,
                "by": MIGRATE,
            }
            if carrier == "HAND" and not m.startswith("hand delivered"):
                rep["review"].append(f"order {o['id']}: shipping method '{method[:20]}…' mapped to HAND")
        inv = o.get("invoice") or {}
        invoice = None
        if any(inv.get(k) for k in ("number", "number1", "number3", "number4")):
            invoice = {k: inv.get(k) for k in ("number", "number1", "number3", "number4") if inv.get(k)}
            invoice["date"] = utc(inv.get("date"))
        files = [
            {
                "legacyFile": f["file"],
                "name": f.get("name") or f["file"],
                "kind": FILE_KINDS.get(f.get("type"), "upload"),
            }
            for f in o.get("files") or []
        ]
        base = {
            "status": status,
            "customer": o["customer"],
            "customerSnapshot": {
                "firstname": o.get("firstname", ""),
                "lastname": o.get("lastname", ""),
                "email": acc["email"] if acc else "",
            },
            "organisationId": acc.get("organisationId") if acc else None,
            "shipTo": contact(o["shipto"], unknown),
            "billTo": contact(o["billedto"], unknown),
            "notes": None,
            "createdAt": submitted,
            "updatedAt": NOW,
            "submittedAt": submitted,
            "history": [status_change(status, NOW)],
            "outbox": [],
            "version": 1,
            "shipping": shipping,
            "invoice": invoice,
            "files": [],
        }
        if status == "CANCELLED":
            base["cancellation"] = {"by": MIGRATE, "at": NOW, "reason": "Cancelled in legacy system", "auto": False}

        def lines(items: list[dict[str, Any]], prefix: str, o: dict[str, Any] = o) -> list[dict[str, Any]]:
            res = []
            for i, it in enumerate(items):
                p = products_by_id.get(it["id"])
                if p is None:
                    rep["warnings"].append(f"order {o['id']}: line product {it['id']} unknown (snapshot empty)")
                line = {
                    "lineId": f"{prefix}{i + 1}",
                    "productId": it["id"],
                    "product": snapshot(p),
                    "qty": max(1, int(it.get("count") or 1)),
                    "picked": [
                        {
                            "barcode": x.get("barcode"),
                            "pickedby": x.get("pickedby"),
                            "pickeddate": utc(x.get("pickeddate")),
                        }
                        if isinstance(x, dict)
                        else {"barcode": str(x), "pickedby": None, "pickeddate": None}
                        for x in it.get("picked") or []
                    ],
                }
                if it.get("cost") not in (None, ""):
                    line["legacy"] = {"lineCost": money(it["cost"])}
                res.append(line)
            return res

        paid, pro = o.get("cart") or [], o.get("ncicart") or []
        legacy = {
            "total": money(o.get("total")),
            "shippingEstimate": money(o.get("shippingestimate")),
            "shippingCost1": money(sh.get("cost1")),
            "paid": bool(o.get("paid")),
            "files": files,
        }
        if paid:
            out.append(
                {"id": o["id"], "type": "PAID", "currency": "BBD", "lines": lines(paid, "L"), **base, "legacy": legacy}
            )
        if pro:
            pid = o["id"] if not paid else "ORD" + secrets.token_hex(16)
            doc = {
                "id": pid,
                "type": "PROBONO",
                "currency": None,
                "lines": lines(pro, "P"),
                **base,
                "legacy": legacy if not paid else {"files": []},
            }
            if paid:
                note = {**status_change(status, NOW), "reason": f"{REASON}; split from {o['id']}"}
                doc["history"] = [note]
                out[-1]["history"][0]["reason"] = f"{REASON}; Pro Bono lines moved to {pid}"
                rep["review"].append(f"order {o['id']}: split, Pro Bono lines -> {pid}")
            out.append(doc)
        if not paid and not pro:
            rep["warnings"].append(f"order {o['id']}: no lines, skipped")
    rep["counts"]["orders"] = Counter(f"{d['type']}/{d['status']}" for d in out)
    return out


def main() -> None:
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    dst.mkdir(parents=True, exist_ok=True)
    rep: dict[str, Any] = {"generatedAt": NOW.isoformat(), "counts": {}, "warnings": [], "review": []}
    unknown_countries: Counter = Counter()
    accounts, orders = load(src, "accounts"), load(src, "orders")
    products, storage = load(src, "product"), load(src, "storage")
    history, misc = load(src, "history"), load(src, "misc")
    rep["source"] = {
        "accounts": len(accounts),
        "orders": len(orders),
        "product": len(products),
        "storage": len(storage),
        "history": len(history),
        "misc": len(misc),
    }

    accounts_v2, organisations = m02_accounts(accounts, orders, rep, unknown_countries)
    by_acc = {a["id"]: a for a in accounts_v2}
    misc_v2, project_codes = m01_misc(misc, products, by_acc, rep)
    products_v2 = m03_products(products, project_codes, rep)
    by_prod = {p["id"]: p for p in products_v2}
    units, stock = m04_storage(storage, products_v2, rep)
    history_v2 = m05_history(history, units, rep)
    orders_v2 = m06_carts(accounts, by_prod, rep) + m07_orders(orders, by_acc, by_prod, rep, unknown_countries)
    if unknown_countries:
        rep["review"].append(
            f"{sum(unknown_countries.values())} address(es) with an unmapped country: "
            + ", ".join(sorted(unknown_countries))
        )

    for name, docs in {
        "accounts": accounts_v2,
        "organisations": organisations,
        "misc": misc_v2,
        "product": products_v2,
        "storage": units,
        "stock": stock,
        "history": history_v2,
        "orders": orders_v2,
    }.items():
        (dst / f"{name}.json").write_text(
            json_util.dumps(docs, json_options=json_util.CANONICAL_JSON_OPTIONS), encoding="utf-8"
        )
    rep["mappings"] = mapping_tables(local=False)
    (dst / "report.json").write_text(json.dumps(rep, indent=2, default=dict), encoding="utf-8")
    # Full table incl. personal free text: stays next to the export (git-ignored `db/`), for the reviewers only.
    (dst / "mappings.local.json").write_text(json.dumps(mapping_tables(local=True), indent=2), encoding="utf-8")
    print(
        json.dumps(
            {"counts": rep["counts"], "warnings": len(rep["warnings"]), "review": len(rep["review"])},
            indent=1,
            default=dict,
        )
    )


if __name__ == "__main__":
    main()
