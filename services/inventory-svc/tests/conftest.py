from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import fakeredis.aioredis
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from jwt.algorithms import OKPAlgorithm

from cimh_common.auth import JwksCache, TokenVerifier
from cimh_common.testing import AsyncMongoMock
from inventory_svc.config import Settings
from inventory_svc.main import BASE, build_app

KEY = Ed25519PrivateKey.generate()
SCHEMAS = Path(__file__).resolve().parents[3] / "packages" / "event-schemas" / "schemas"


async def jwks() -> dict[str, Any]:
    jwk: dict[str, Any] = OKPAlgorithm.to_jwk(KEY.public_key(), as_dict=True)
    jwk["kid"] = "k1"
    return {"keys": [jwk]}


def verifier() -> TokenVerifier:
    return TokenVerifier(JwksCache(jwks), issuer="i", audience="a")


def token(role: str, sub: str = "USR1", email: str = "x@example.org", mfa: bool = True) -> dict[str, str]:
    now = int(time.time())
    claims = {"iss": "i", "aud": "a", "sub": sub, "role": role, "email": email, "jti": f"j-{sub}-{role}",
              "iat": now, "exp": now + 300, "mfa": mfa}  # fmt: skip
    return {"Authorization": "Bearer " + jwt.encode(claims, KEY, algorithm="EdDSA", headers={"kid": "k1"})}


STAFF = token("staff", "USRSTAFF", "s@cimh.edu.bb")
STAFF2 = token("staff", "USRSTAFF2", "t@cimh.edu.bb")
ADMIN = token("admin", "USRADMIN", "a@cimh.edu.bb")
USER = token("user", "USRUSER", "u@met.bb")
ORDER = token("service", "svc:order", "")
CATALOG = token("service", "svc:catalog", "")


@dataclass
class MemoryPlaces:
    """In-memory stand-in for catalog-svc's /internal/places (same filters, upsert by barcode)."""

    items: dict[str, dict[str, Any]] = field(default_factory=dict)
    calls: int = 0
    catalog: dict[str, dict[str, Any]] = field(default_factory=dict)  # products only catalog-svc knows

    async def list(
        self,
        *,
        kind: str | None = None,
        site: str | None = None,
        location: str | None = None,
        barcode: str | None = None,
    ) -> list[dict[str, Any]]:
        self.calls += 1
        out = []
        for p in sorted(self.items.values(), key=lambda x: (x["kind"], x["barcode"])):
            want = {"kind": kind, "site": site, "location": location, "barcode": barcode}
            if all(v is None or p.get(k) == v for k, v in want.items()):
                out.append(dict(p))
        return out

    async def put(self, place: dict[str, Any]) -> dict[str, Any]:
        self.items[place["barcode"]] = {"site": None, "location": None, "number": None, **place}
        return dict(self.items[place["barcode"]])

    async def products(self, ids: list[str]) -> list[dict[str, Any]]:
        return [self.catalog[i] for i in ids if i in self.catalog]


def event_schema(etype: str) -> Draft202012Validator:
    index = json.loads((SCHEMAS / "index.json").read_text(encoding="utf-8"))
    return Draft202012Validator(json.loads((SCHEMAS / index[etype]).read_text(encoding="utf-8")))


def check_event(evt: dict[str, Any]) -> None:
    raw = {k: v for k, v in evt.items() if k != "attempts"}
    event_schema(evt["type"]).validate(json.loads(json.dumps(raw, default=str)))


@dataclass
class Ctx:
    client: TestClient
    db: Any
    places: MemoryPlaces

    def url(self, path: str) -> str:
        return BASE + path

    def run(self, coro: Any) -> Any:
        return asyncio.run(coro)

    def product(self, pid: str, name: str = "Rain gauge", threshold: int = 0, active: bool = True) -> None:
        """What the catalog consumer would have stored."""
        doc = {"id": pid, "productName": name, "type": "MET", "threshold": threshold, "active": active,
               "available": 0, "reserved": 0, "picked": 0, "assigned": 0, "low": active and threshold > 0,
               "outbox": []}  # fmt: skip
        self.run(self.db["stock"].insert_one(doc))

    def shelves(self, count: int = 2, site_name: str = "Husbands", loc_name: str = "Store A") -> list[str]:
        site = self.client.post(self.url("/sites"), headers=STAFF, json={"name": site_name, "country": "BB"})
        assert site.status_code == 201, site.text
        loc = self.client.post(
            self.url(f"/sites/{site.json()['barcode']}/locations"), headers=STAFF, json={"name": loc_name}
        )
        assert loc.status_code == 201, loc.text
        r = self.client.post(
            self.url(f"/locations/{loc.json()['barcode']}/shelves"), headers=STAFF, json={"count": count}
        )
        assert r.status_code == 201, r.text
        return [s["barcode"] for s in r.json()["items"]]

    def labels(self, pid: str, n: int = 1) -> list[str]:
        r = self.client.post(self.url("/labels"), headers=STAFF, json={"productId": pid, "quantity": n})
        assert r.status_code == 201, r.text
        return list(r.json()["barcodes"])

    def scan(self, op: str, body: dict[str, Any], headers: dict[str, str] | None = None, key: str | None = None) -> Any:
        h = {**(headers or STAFF), "Idempotency-Key": key or uuid.uuid4().hex}
        return self.client.post(self.url(f"/{op}"), headers=h, json=body)

    def stock_doc(self, pid: str) -> dict[str, Any]:
        doc: dict[str, Any] = self.run(self.db["stock"].find_one({"id": pid}))
        return doc

    def events(self, pid: str, etype: str | None = None) -> list[dict[str, Any]]:
        out = [e for e in self.stock_doc(pid).get("outbox", []) if etype is None or e["type"] == etype]
        for e in out:
            check_event(e)
        return out

    def history(self, unit: str) -> list[dict[str, Any]]:
        docs: list[dict[str, Any]] = self.run(self.db["history"].find({"id": unit}).sort("date", 1).to_list())
        return docs


@pytest.fixture
def ctx() -> Iterator[Ctx]:
    db = AsyncMongoMock()
    places = MemoryPlaces()
    app = build_app(
        Settings(),
        db=db,
        redis=fakeredis.aioredis.FakeRedis(),
        token_verifier=verifier(),
        places=places,
        configure_logs=False,
    )
    with TestClient(app) as client:
        yield Ctx(client, db, places)


def ts(seconds: int = 0) -> datetime:
    return datetime(2026, 1, 1, tzinfo=UTC).replace(second=seconds)
