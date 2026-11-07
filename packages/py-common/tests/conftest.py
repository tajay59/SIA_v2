from __future__ import annotations

import time
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from jwt.algorithms import OKPAlgorithm

from cimh_common.auth import JwksCache, TokenVerifier

ISSUER = "https://identity.test"
AUDIENCE = "cimh-stores"


class Keys:
    def __init__(self) -> None:
        self.private = Ed25519PrivateKey.generate()
        self.kid = "test-key-1"

    def jwks(self) -> dict[str, Any]:
        jwk: dict[str, Any] = OKPAlgorithm.to_jwk(self.private.public_key(), as_dict=True)
        jwk["kid"] = self.kid
        return {"keys": [jwk]}

    def token(self, sub: str = "USR1", role: str = "user", **extra: Any) -> str:
        now = int(time.time())
        claims: dict[str, Any] = {
            "iss": ISSUER,
            "aud": AUDIENCE,
            "sub": sub,
            "role": role,
            "jti": f"jti-{sub}-{now}",
            "iat": now,
            "exp": now + 900,
            "mfa": True,
            "email": f"{sub.lower()}@example.org",
        }
        claims.update(extra)
        return jwt.encode(claims, self.private, algorithm="EdDSA", headers={"kid": self.kid})


@pytest.fixture
def keys() -> Keys:
    return Keys()


@pytest.fixture
def revoked() -> set[str]:
    return set()


@pytest.fixture
def verifier(keys: Keys, revoked: set[str]) -> TokenVerifier:
    async def fetch() -> dict[str, Any]:
        return keys.jwks()

    async def is_revoked(jti: str, sid: str | None) -> bool:
        return jti in revoked or (sid is not None and sid in revoked)

    return TokenVerifier(JwksCache(fetch), issuer=ISSUER, audience=AUDIENCE, is_revoked=is_revoked)
