"""Integration: catalog-svc on a real MongoDB: the text index and ranked search, staff serial lookups, the
`xuser` view (created by the service) and its field list. mongomock has no $text and no views.
"""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from jwt.algorithms import OKPAlgorithm

pytestmark = pytest.mark.integration

KEY = Ed25519PrivateKey.generate()


async def _jwks() -> dict[str, Any]:
    jwk: dict[str, Any] = OKPAlgorithm.to_jwk(KEY.public_key(), as_dict=True)
    jwk["kid"] = "k1"
    return {"keys": [jwk]}


def _staff() -> dict[str, str]:
    now = int(time.time())
    claims = {"iss": "i", "aud": "a", "sub": "USRS", "role": "staff", "email": "s@cimh.edu.bb", "jti": "j",
              "iat": now, "exp": now + 300, "mfa": True}  # fmt: skip
    return {"Authorization": "Bearer " + jwt.encode(claims, KEY, algorithm="EdDSA", headers={"kid": "k1"})}


def test_search_and_xuser_view_on_real_mongo(stack: Any, tmp_path: Path) -> None:
    from pymongo import AsyncMongoClient

    from catalog_svc.config import Settings
    from catalog_svc.main import build_app
    from catalog_svc.store import PUBLIC_FIELDS
    from cimh_common.auth import JwksCache, TokenVerifier

    name = f"itest_{uuid.uuid4().hex[:8]}"
    db = AsyncMongoClient(stack.mongo_url, tz_aware=True)[name]
    app = build_app(
        Settings(media_root=str(tmp_path)),
        db=db,
        token_verifier=TokenVerifier(JwksCache(_jwks), issuer="i", audience="a"),
        configure_logs=False,
    )
    staff = _staff()
    base = "/api/catalog/v1"
    with TestClient(app) as client:

        def make(**kw: Any) -> dict[str, Any]:
            body = {"type": "MET", "department": "Met", "sellable": True, "probono": False, "threshold": 0, **kw}
            r = client.post(f"{base}/products", headers=staff, json=body)
            assert r.status_code == 201, r.text
            return dict(r.json())

        gauge = make(name="Tipping bucket rain gauge", keywords=["rain", "precipitation"], cost="10.00")
        make(name="Rain shield", make="Acme")
        make(name="Barometer", modelnumber="RG-9000", sn="SN-777", keywords=["pressure"])
        make(name="Rain logger (staff only)", sellable=False)
        for i in range(3):
            make(name=f"Anemometer {i}", keywords=["wind"])

        r = client.get(f"{base}/products/search", params={"q": "rain gauge"})
        assert r.status_code == 200, r.text
        names = [i["name"] for i in r.json()["items"]]
        assert names[0] == "Tipping bucket rain gauge"  # matches both words, name weight 10
        assert "Rain shield" in names
        assert "Rain logger (staff only)" not in names  # customers: sellable only
        assert set(r.json()["items"][0]) == set(PUBLIC_FIELDS)

        staff_names = [
            i["name"]
            for i in client.get(f"{base}/products/search", headers=staff, params={"q": "rain"}).json()["items"]
        ]
        assert "Rain logger (staff only)" in staff_names
        # Staff: serial and model-number prefixes, listed first; customers can't search by serial.
        serial = client.get(f"{base}/products/search", headers=staff, params={"q": "SN-7"}).json()["items"]
        assert serial[0]["name"] == "Barometer"
        assert client.get(f"{base}/products/search", params={"q": "SN-7"}).json()["items"] == []

        page1 = client.get(f"{base}/products/search", params={"q": "wind", "limit": 2}).json()
        assert len(page1["items"]) == 2
        page2 = client.get(f"{base}/products/search", params={"q": "wind", "limit": 2, "cursor": page1["nextCursor"]})
        assert len(page2.json()["items"]) == 1
        assert page2.json()["nextCursor"] is None

    # The async client is bound to the TestClient's event loop: read the view with a plain client.
    from pymongo import MongoClient

    sync = MongoClient(stack.mongo_url)
    rows = list(sync[name]["xuser"].find({}))
    assert {r["name"] for r in rows} >= {"Tipping bucket rain gauge", "Barometer"}
    assert "Rain logger (staff only)" not in {r["name"] for r in rows}
    for row in rows:
        assert set(row) <= set(PUBLIC_FIELDS)  # the view can never leak cost, serials or the outbox
    assert gauge["cost"] == "10.00"
    sync.drop_database(name)
    sync.close()
