"""Generated authz tests for hello-svc from tests/authz/matrix.yaml (TEST_STRATEGY §5).

Every service copies this pattern: parametrize over `cases_for` for its base path and
supply own/other resources through fixtures.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from jwt.algorithms import OKPAlgorithm

from cimh_common.auth import JwksCache, TokenVerifier
from hello_svc.main import build_app

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools" / "authz"))
from authz_cases import Case, cases_for, endpoints_for

KEY = Ed25519PrivateKey.generate()
CASES = [c for ep, row in endpoints_for("/api/hello/v1").items() for c in cases_for(ep, row)]


async def _jwks() -> dict[str, Any]:
    jwk: dict[str, Any] = OKPAlgorithm.to_jwk(KEY.public_key(), as_dict=True)
    jwk["kid"] = "k1"
    return {"keys": [jwk]}


def _headers(actor: str) -> dict[str, str]:
    if actor == "anonymous":
        return {}
    role = "user" if actor == "cimh_user" else actor
    email = "x@cimh.edu.bb" if actor == "cimh_user" else "x@example.org"
    now = int(time.time())
    claims = {
        "iss": "i",
        "aud": "a",
        "sub": "USR1",
        "role": role,
        "email": email,
        "jti": "j",
        "iat": now,
        "exp": now + 60,
    }
    return {"Authorization": "Bearer " + jwt.encode(claims, KEY, algorithm="EdDSA", headers={"kid": "k1"})}


@pytest.fixture(scope="module")
def client() -> TestClient:
    verifier = TokenVerifier(JwksCache(_jwks), issuer="i", audience="a")
    return TestClient(build_app(token_verifier=verifier, readiness_checks={}, configure_logs=False))


def test_cases_were_generated() -> None:
    assert len(CASES) >= 9


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_authz(client: TestClient, case: Case) -> None:
    method, path = case.endpoint.split(" ", 1)
    r = client.request(method, path, headers=_headers(case.actor))
    if case.expect == "2xx":
        assert 200 <= r.status_code < 300, r.text
    else:
        assert r.status_code == case.expect, r.text
    if case.code:
        assert r.json().get("code") == case.code
