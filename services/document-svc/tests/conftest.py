from __future__ import annotations

import json
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from jwt.algorithms import OKPAlgorithm

from cimh_common.auth import JwksCache, TokenVerifier
from cimh_common.consumer import envelope_bytes
from cimh_common.errors import ProblemError
from cimh_common.outbox import EventEnvelope
from document_svc.clients import unavailable
from document_svc.config import Settings
from document_svc.files import ScannerDown
from document_svc.main import BASE, build_app

KEY = Ed25519PrivateKey.generate()
SCHEMAS = Path(__file__).resolve().parents[3] / "packages" / "event-schemas" / "schemas"
# The standard anti-virus test file (not a virus; every scanner reports it as Eicar-Test-Signature).
EICAR = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


async def jwks() -> dict[str, Any]:
    jwk: dict[str, Any] = OKPAlgorithm.to_jwk(KEY.public_key(), as_dict=True)
    jwk["kid"] = "k1"
    return {"keys": [jwk]}


def verifier() -> TokenVerifier:
    return TokenVerifier(JwksCache(jwks), issuer="i", audience="a")


def token(
    role: str, sub: str, email: str = "x@example.org", mfa: bool = True, org: str | None = None
) -> dict[str, str]:
    now = int(time.time())
    claims = {"iss": "i", "aud": "a", "sub": sub, "role": role, "email": email, "jti": f"j-{sub}-{role}",
              "iat": now, "exp": now + 300, "mfa": mfa, "org": org}  # fmt: skip
    return {"Authorization": "Bearer " + jwt.encode(claims, KEY, algorithm="EdDSA", headers={"kid": "k1"})}


USER = token("user", "USRUSER", "u@met.bb", org="ORGMET")
PEER = token("user", "USRPEER", "p@met.bb", org="ORGMET")
OTHER = token("user", "USROTHER", "o@else.org", org="ORGELSE")
STAFF = token("staff", "USRSTAFF", "s@cimh.edu.bb")
ADMIN = token("admin", "USRADMIN", "a@cimh.edu.bb")
INVENTORY = token("service", "svc:inventory", "")
CATALOG = token("service", "svc:catalog", "")


def request_doc(rid: str, status: str = "AWAITING_AGREEMENT", **kw: Any) -> dict[str, Any]:
    return {
        "id": rid, "type": kw.pop("type", "PAID"), "status": status, "customer": "USRUSER",
        "customerName": "Una User", "organisationId": "ORGMET", "organisationName": "Met Office", "currency": "BBD",
        "lines": [
            {"lineId": "L1", "productId": "MET1", "product": {"name": "Rain gauge", "make": "Acme"}, "qty": 2,
             "choice": None},
            {"lineId": "L2", "productId": "MET2", "product": {"name": "Anemometer"}, "qty": 1, "choice": None},
        ],
        "shipTo": {"line1": "Husbands", "city": "St James", "country": "BB", "firstname": "Una", "lastname": "User",
                   "email": "u@met.bb"},
        "billTo": None,
        "quotes": [{"id": "Q1", "version": 1, "total": "540.00", "expiresAt": "2026-12-08T00:00:00Z",
                    "lines": [{"lineId": "L1", "unitPrice": "180.00", "total": "360.00"},
                              {"lineId": "L2", "unitPrice": "180.00", "total": "180.00"}]}],
        "cimhQuote": {"version": 1, "exchangeRate": None, "total": "300.00", "fileId": None,
                      "lines": [{"lineId": "L1", "unitPrice": "150.00", "total": "300.00"}]},
        "adminFee": "25.00",
        "agreement": {"quoteVersion": 1, "choices": [{"lineId": "L1", "choice": "CIMH"},
                                                     {"lineId": "L2", "choice": "SUPPLIER"}],
                      "total": "505.00", "fileId": None},
        "shipping": None, "invoice": None, "quoteExpiresAt": "2026-12-08T00:00:00Z",
        **kw,
    }  # fmt: skip


ACCOUNTS = {
    "USRUSER": {"role": "user", "org": "ORGMET"},
    "USRPEER": {"role": "user", "org": "ORGMET"},
    "USROTHER": {"role": "user", "org": "ORGELSE"},
    "USRSTAFF": {"role": "staff", "org": None},
    "USRADMIN": {"role": "admin", "org": None},
}


@dataclass
class MemoryOrders:
    """order-svc's internal answers, same rules as OrderService.access."""

    requests: dict[str, dict[str, Any]] = field(default_factory=dict)
    attached: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    down: bool = False

    async def access(self, rid: str, user: str) -> dict[str, Any] | None:
        if self.down:
            raise unavailable("order-svc")
        doc = self.requests.get(rid)
        if doc is None:
            return None
        out = {"allowed": False, "canAct": False, "status": doc["status"], "type": doc["type"]}
        acc = ACCOUNTS.get(user)
        if acc is None:
            return out
        if acc["role"] in ("staff", "admin") or doc["customer"] == user:
            return out | {"allowed": True, "canAct": acc["role"] == "admin" or doc["customer"] == user}
        return out | {"allowed": acc["org"] == doc.get("organisationId")}

    async def request(self, rid: str) -> dict[str, Any] | None:
        if self.down:
            raise unavailable("order-svc")
        return self.requests.get(rid)

    async def attach(self, rid: str, file: dict[str, Any]) -> None:
        if self.down:
            raise unavailable("order-svc")
        self.attached.append((rid, file))


@dataclass
class MemoryPublisher:
    sent: list[tuple[str, str, EventEnvelope]] = field(default_factory=list)
    down: bool = False

    async def publish(self, topic: str, key: str, event: EventEnvelope) -> None:
        if self.down:
            raise ProblemError(503, "DEPENDENCY_UNAVAILABLE", "Kafka is unavailable")
        self.sent.append((topic, key, event))

    def types(self, topic: str = "document.events") -> list[str]:
        return [e.type for t, _, e in self.sent if t == topic]


@dataclass
class FakeClamd:
    """Finds EICAR like clamd does."""

    down: bool = False
    scanned: int = 0

    async def scan(self, data: bytes) -> str | None:
        if self.down:
            raise ScannerDown("connection refused")
        self.scanned += 1
        return "Eicar-Test-Signature" if data.startswith(EICAR) else None  # clamd matches it at offset 0

    async def ready(self) -> bool:
        return not self.down


def event_schema(etype: str) -> Draft202012Validator:
    index = json.loads((SCHEMAS / "index.json").read_text(encoding="utf-8"))
    return Draft202012Validator(json.loads((SCHEMAS / index[etype]).read_text(encoding="utf-8")))


def check_event(event: EventEnvelope) -> None:
    event_schema(event.type).validate(json.loads(envelope_bytes(event)))


@dataclass
class Ctx:
    client: TestClient
    orders: MemoryOrders
    publisher: MemoryPublisher
    scanner: FakeClamd
    root: Path

    @staticmethod
    def url(path: str) -> str:
        return BASE + path

    def upload(self, rid: str, kind: str = "signed_agreement", data: bytes = PDF, name: str = "signed.pdf",
               headers: dict[str, str] | None = None) -> Any:  # fmt: skip
        return self.client.post(
            self.url("/files"),
            headers=headers or USER,
            data={"requestId": rid, "kind": kind},
            files={"file": (name, data, "application/octet-stream")},
        )


def make_app(root: Path, orders: MemoryOrders, publisher: MemoryPublisher, scanner: FakeClamd, **kw: Any) -> Any:
    return build_app(
        Settings(data_dir=str(root), **kw),
        token_verifier=verifier(),
        orders=orders,
        publisher=publisher,
        scanner=scanner,
        configure_logs=False,
    )


@pytest.fixture
def ctx(tmp_path: Path) -> Iterator[Ctx]:
    orders = MemoryOrders(requests={"ORD1": request_doc("ORD1")})
    publisher, scanner = MemoryPublisher(), FakeClamd()
    app = make_app(tmp_path, orders, publisher, scanner)
    with TestClient(app) as client:
        yield Ctx(client, orders, publisher, scanner, tmp_path)
