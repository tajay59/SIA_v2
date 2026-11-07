from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from jwt.algorithms import OKPAlgorithm

from catalog_svc.config import Settings
from catalog_svc.main import BASE, build_app
from cimh_common.auth import JwksCache, TokenVerifier
from cimh_common.testing import AsyncMongoMock

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
    claims = {
        "iss": "i",
        "aud": "a",
        "sub": sub,
        "role": role,
        "email": email,
        "jti": f"j-{sub}-{role}",
        "iat": now,
        "exp": now + 300,
        "mfa": mfa,
    }
    return {"Authorization": "Bearer " + jwt.encode(claims, KEY, algorithm="EdDSA", headers={"kid": "k1"})}


STAFF = token("staff", "USRSTAFF", "s@cimh.edu.bb")
ADMIN = token("admin", "USRADMIN", "a@cimh.edu.bb")
USER = token("user", "USRUSER", "u@met.bb")
INVENTORY = token("service", "svc:inventory", "")
ORDER = token("service", "svc:order", "")

ACCOUNTS = {
    "USRSTAFF": {"id": "USRSTAFF", "email": "s@cimh.edu.bb", "firstname": "Sam", "lastname": "Staff", "role": "staff"},
    "USRADMIN": {"id": "USRADMIN", "email": "a@cimh.edu.bb", "firstname": "Ada", "lastname": "Admin", "role": "admin"},
    "USRUSER": {"id": "USRUSER", "email": "u@met.bb", "firstname": "Uma", "lastname": "User", "role": "user"},
    "USROFF": {"id": "USROFF", "email": "o@cimh.edu.bb", "firstname": "Old", "lastname": "Staff", "role": "staff"},
}


async def lookup(account_id: str) -> dict[str, Any] | None:
    acc = ACCOUNTS.get(account_id)
    if acc is None:
        return None
    return {**acc, "status": "SUSPENDED" if account_id == "USROFF" else "ACTIVE"}


def event_schema(etype: str) -> Draft202012Validator:
    index = json.loads((SCHEMAS / "index.json").read_text(encoding="utf-8"))
    return Draft202012Validator(json.loads((SCHEMAS / index[etype]).read_text(encoding="utf-8")))


def check_event(evt: dict[str, Any]) -> None:
    event_schema(evt["type"]).validate(json.loads(json.dumps(evt, default=str)))


class Ctx:
    def __init__(self, media_root: Path, **settings: Any) -> None:
        self.db = AsyncMongoMock()
        self.settings = Settings(media_root=str(media_root), **settings)
        self.app = build_app(
            self.settings,
            db=self.db,
            token_verifier=verifier(),
            lookup_account=lookup,
            configure_logs=False,
            create_view=False,
        )
        self.client = TestClient(self.app)
        self.loop = asyncio.new_event_loop()
        self.media = media_root

    def run(self, coro: Any) -> Any:
        return self.loop.run_until_complete(coro)

    def url(self, path: str) -> str:
        return BASE + path

    def product(self, pid: str) -> dict[str, Any]:
        return dict(self.run(self.db["product"].find_one({"id": pid})))

    def misc(self, mid: str) -> dict[str, Any]:
        return dict(self.run(self.db["misc"].find_one({"id": mid})))

    def create(self, **over: Any) -> dict[str, Any]:
        body = {
            "name": "Rain gauge",
            "type": "MET",
            "department": "Meteorology",
            "sellable": True,
            "probono": False,
            "threshold": 2,
            "cost": "1250.00",
            "make": "Acme",
            "modelnumber": "RG-200",
            "sn": "SN-0001",
            "keywords": ["Rain", "gauge", "rain"],
            **over,
        }
        r = self.client.post(self.url("/products"), headers=STAFF, json=body)
        assert r.status_code == 201, r.text
        return dict(r.json())


@pytest.fixture
def ctx(tmp_path: Path) -> Iterator[Ctx]:
    c = Ctx(tmp_path)
    with c.client:
        yield c
    c.loop.close()
