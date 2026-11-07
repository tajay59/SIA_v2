from __future__ import annotations

import time
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from jwt.algorithms import OKPAlgorithm

from cimh_common.auth import JwksCache, TokenVerifier
from hello_svc.main import build_app

KEY = Ed25519PrivateKey.generate()


async def _jwks() -> dict[str, Any]:
    jwk: dict[str, Any] = OKPAlgorithm.to_jwk(KEY.public_key(), as_dict=True)
    jwk["kid"] = "k1"
    return {"keys": [jwk]}


def _token(role: str) -> str:
    now = int(time.time())
    claims = {"iss": "i", "aud": "a", "sub": "USR1", "role": role, "jti": "j", "iat": now, "exp": now + 60, "mfa": True}
    return jwt.encode(claims, KEY, algorithm="EdDSA", headers={"kid": "k1"})


def client() -> TestClient:
    verifier = TokenVerifier(JwksCache(_jwks), issuer="i", audience="a")
    return TestClient(build_app(token_verifier=verifier, readiness_checks={}, configure_logs=False))


def test_greeting_public() -> None:
    r = client().get("/api/hello/v1/greeting")
    assert r.status_code == 200
    assert r.json()["service"] == "hello-svc"


def test_health() -> None:
    c = client()
    assert c.get("/health/live").status_code == 200
    assert c.get("/health/ready").status_code == 200


def test_whoami_requires_auth() -> None:
    c = client()
    assert c.get("/api/hello/v1/whoami").status_code == 401
    r = c.get("/api/hello/v1/whoami", headers={"Authorization": f"Bearer {_token('user')}"})
    assert r.json() == {"sub": "USR1", "role": "user"}


def test_staff_only() -> None:
    c = client()
    assert c.get("/api/hello/v1/staff-only", headers={"Authorization": f"Bearer {_token('user')}"}).status_code == 403
    assert c.get("/api/hello/v1/staff-only", headers={"Authorization": f"Bearer {_token('staff')}"}).status_code == 200


def test_unconfigured_verifier_is_503() -> None:
    c = TestClient(build_app(token_verifier=None, readiness_checks={}, configure_logs=False))
    assert c.get("/api/hello/v1/whoami", headers={"Authorization": "Bearer x"}).status_code == 503


def test_env_readiness_wiring(monkeypatch: Any) -> None:
    monkeypatch.setenv("MONGO_URL", "mongodb://127.0.0.1:1/?directConnection=true")
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/0")
    monkeypatch.setenv("JWKS_URL", "http://127.0.0.1:1/jwks")
    app = build_app(configure_logs=False)
    assert set(app.state.readiness_checks) == {"mongo", "redis"}
    assert app.state.token_verifier is not None
