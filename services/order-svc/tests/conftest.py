from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from decimal import Decimal
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
from cimh_common.errors import ProblemError
from cimh_common.testing import AsyncMongoMock
from order_svc.config import Settings
from order_svc.main import BASE, build_app

KEY = Ed25519PrivateKey.generate()
SCHEMAS = Path(__file__).resolve().parents[3] / "packages" / "event-schemas" / "schemas"


async def jwks() -> dict[str, Any]:
    jwk: dict[str, Any] = OKPAlgorithm.to_jwk(KEY.public_key(), as_dict=True)
    jwk["kid"] = "k1"
    return {"keys": [jwk]}


def verifier() -> TokenVerifier:
    return TokenVerifier(JwksCache(jwks), issuer="i", audience="a")


def token(
    role: str, sub: str = "USR1", email: str = "x@example.org", mfa: bool = True, org: str | None = None
) -> dict[str, str]:
    now = int(time.time())
    claims = {"iss": "i", "aud": "a", "sub": sub, "role": role, "email": email, "jti": f"j-{sub}-{role}",
              "iat": now, "exp": now + 300, "mfa": mfa, "org": org}  # fmt: skip
    return {"Authorization": "Bearer " + jwt.encode(claims, KEY, algorithm="EdDSA", headers={"kid": "k1"})}


USER = token("user", "USRUSER", "u@met.bb", org="ORGMET")
PEER = token("user", "USRPEER", "p@met.bb", org="ORGMET")  # same organisation
OTHER = token("user", "USROTHER", "o@else.org", org="ORGELSE")
CIMH_USER = token("user", "USRCIMH", "c@cimh.edu.bb")
STAFF = token("staff", "USRSTAFF", "s@cimh.edu.bb")
ADMIN = token("admin", "USRADMIN", "a@cimh.edu.bb")
DOCUMENT = token("service", "svc:document", "")
ADDRESS = {"line1": "Husbands", "city": "St James", "country": "BB", "firstname": "Una", "lastname": "User",
           "email": "u@met.bb"}  # fmt: skip


def product(pid: str, *, probono: bool = False, cost: str | None = "100.00", **kw: Any) -> dict[str, Any]:
    return {"id": pid, "name": f"Product {pid}", "type": "MET", "department": "Met", "probono": probono,
            "probonoMaxPerRequest": kw.pop("cap", None), "images": [], "inStock": True, "sellable": not probono,
            "active": True, "cost": cost, "threshold": 0, "version": 1, "make": None, "modelname": None,
            "modelnumber": None, **kw}  # fmt: skip


@dataclass
class MemoryDeps:
    """In-memory catalog + inventory + identity, same answers as the HTTP clients."""

    catalog: dict[str, dict[str, Any]] = field(default_factory=dict)
    fee: Decimal = Decimal("0")
    stock: dict[str, int] = field(default_factory=dict)  # productId -> available units
    accounts: dict[str, dict[str, Any]] = field(default_factory=dict)
    picks: list[tuple[str, str, str]] = field(default_factory=list)
    reserved: dict[str, set[str]] = field(default_factory=dict)  # orderId -> units inventory reserved
    down: bool = False

    def _up(self) -> None:
        if self.down:
            raise ProblemError(503, "DEPENDENCY_UNAVAILABLE", "down")

    async def products(self, ids: list[str]) -> list[dict[str, Any]]:
        self._up()
        return [dict(self.catalog[i]) for i in ids if i in self.catalog]

    async def admin_fee(self) -> Decimal:
        self._up()
        return self.fee

    async def availability(self, lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
        self._up()
        out = []
        for ln in lines:
            n = self.stock.get(ln["productId"], 0)
            out.append({"lineId": ln["lineId"], "available": n, "fullQuantity": n >= ln["qty"]})
        return out

    async def pick(self, unit: str, order_id: str, picked_by: str, key: str) -> dict[str, Any]:
        self._up()
        if unit not in self.reserved.get(order_id, set()):
            raise ProblemError(409, "UNIT_NOT_RESERVED_FOR_ORDER", "not reserved")
        self.reserved[order_id].discard(unit)
        self.picks.append((unit, order_id, picked_by))
        return {"barcode": unit, "product": unit.split("_")[0], "picked": True}

    async def account(self, account_id: str) -> dict[str, Any] | None:
        return self.accounts.get(account_id)


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
    deps: MemoryDeps

    def url(self, path: str) -> str:
        return BASE + path

    def run(self, coro: Any) -> Any:
        return asyncio.run(coro)

    @property
    def svc(self) -> Any:
        return self.client.app.state.orders  # type: ignore[attr-defined]

    def doc(self, rid: str) -> dict[str, Any]:
        d: dict[str, Any] = self.run(self.db["orders"].find_one({"id": rid}))
        return d

    def events(self, rid: str, etype: str | None = None) -> list[dict[str, Any]]:
        out = [e for e in self.doc(rid).get("outbox", []) if etype is None or e["type"] == etype]
        for e in out:
            check_event(e)
        return out

    def force(self, rid: str, **fields: Any) -> None:
        self.run(self.db["orders"].update_one({"id": rid}, {"$set": fields}))

    def get(self, rid: str, who: dict[str, str] | None = None) -> dict[str, Any]:
        r = self.client.get(self.url(f"/requests/{rid}"), headers=who or STAFF)
        assert r.status_code == 200, r.text
        body: dict[str, Any] = r.json()
        return body

    def act(
        self, rid: str, action: str, body: Any = None, who: dict[str, str] | None = None, *, method: str = "POST"
    ) -> Any:
        v = self.get(rid, STAFF)["version"]
        return self.client.request(
            method, self.url(f"/requests/{rid}/{action}"), headers={**(who or STAFF), "If-Match": str(v)}, json=body
        )

    def ok(
        self, rid: str, action: str, body: Any = None, who: dict[str, str] | None = None, **kw: Any
    ) -> dict[str, Any]:
        r = self.act(rid, action, body, who, **kw)
        assert r.status_code == 200, f"{action}: {r.status_code} {r.text}"
        out: dict[str, Any] = r.json()
        return out

    def cart_add(self, pid: str, qty: int = 1, who: dict[str, str] | None = None) -> Any:
        return self.client.put(self.url(f"/cart/lines/{pid}"), headers=who or USER, json={"qty": qty})

    def submit(
        self, currency: str | None = "BBD", who: dict[str, str] | None = None, **extra: Any
    ) -> list[dict[str, Any]]:
        body: dict[str, Any] = {"shipTo": ADDRESS, **extra}
        if currency:
            body["currency"] = currency
        r = self.client.post(self.url("/requests"), headers=who or USER, json=body)
        assert r.status_code == 201, r.text
        out: list[dict[str, Any]] = r.json()["requests"]
        return out

    def paid_request(self, *pids: str, qty: int = 2, currency: str = "BBD") -> str:
        for pid in pids or ("MET1",):
            assert self.cart_add(pid, qty).status_code == 200
        reqs = self.submit(currency)
        assert len(reqs) == 1
        assert reqs[0]["type"] == "PAID"
        return str(reqs[0]["id"])

    def attach(self, rid: str, kind: str, fid: str | None = None) -> str:
        fid = fid or "FIL" + uuid.uuid4().hex
        body = {"id": fid, "kind": kind, "name": f"{kind}.pdf", "mime": "application/pdf", "size": 10}
        r = self.client.post(self.url(f"/internal/requests/{rid}/files"), headers=DOCUMENT, json=body)
        assert r.status_code == 204, r.text
        return fid


@pytest.fixture
def ctx() -> Iterator[Ctx]:
    deps = MemoryDeps()
    deps.catalog = {
        "MET1": product("MET1", cost="100.00"),
        "MET2": product("MET2", cost="40.50"),
        "PRO1": product("PRO1", probono=True, cost=None, cap=3),
        "OLD1": product("OLD1", active=False),
    }
    deps.accounts = {
        "USRUSER": {"id": "USRUSER", "firstname": "Una", "lastname": "User", "email": "u@met.bb", "role": "user",
                    "status": "ACTIVE", "isCimh": False, "organisationId": "ORGMET", "organisationName": "Met Office"},
        "USRPEER": {"id": "USRPEER", "firstname": "Pat", "lastname": "Peer", "email": "p@met.bb", "role": "user",
                    "status": "ACTIVE", "isCimh": False, "organisationId": "ORGMET", "organisationName": "Met Office"},
        "USROTHER": {"id": "USROTHER", "firstname": "O", "lastname": "Ther", "email": "o@else.org", "role": "user",
                     "status": "ACTIVE", "isCimh": False, "organisationId": "ORGELSE"},
        "USRSTAFF": {"id": "USRSTAFF", "firstname": "S", "lastname": "Taff", "email": "s@cimh.edu.bb", "role": "staff",
                     "status": "ACTIVE", "isCimh": True, "organisationId": None},
    }  # fmt: skip
    app = build_app(
        Settings(),
        db=AsyncMongoMock(),
        redis=fakeredis.aioredis.FakeRedis(),
        token_verifier=verifier(),
        deps=deps,
        configure_logs=False,
    )
    with TestClient(app) as client:
        yield Ctx(client, app.state.orders.store.db, deps)
