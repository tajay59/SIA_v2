"""Token issuing (TR-AUTH-1/3/9): EdDSA access tokens, rotating opaque refresh tokens with
reuse detection, sessions, revocation, JWKS and service tokens.

Redis keys (all with TTLs):
  sess:<sid>            JSON {sub, role, mfa, exp}   session; absolute expiry (admins 8 h)
  user_sess:<sub>       SET of sids                  for "revoke all"
  rt:<sha256(token)>    sid                          current refresh token (single use)
  rt_used:<sha256>      sub                          used refresh tokens, for reuse detection
  revoked:session:<sid> 1                            checked by every service (py-common)
  revoked:jti:<jti>     1
  totp_step:<sub>       last accepted TOTP step       replay protection
"""

from __future__ import annotations

import hashlib
import json
import secrets
import time
from dataclasses import dataclass
from typing import Any

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from jwt.algorithms import OKPAlgorithm

from cimh_common.ids import ulid

from .config import Settings


def _kid(public_key: Ed25519PublicKey) -> str:
    raw = public_key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return hashlib.sha256(raw).hexdigest()[:16]


def _sha(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass(frozen=True)
class IssuedTokens:
    access_token: str
    refresh_token: str
    expires_in: int
    session_id: str


class TokenError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class KeyRing:
    def __init__(self, private_pem: str | None, previous_public_pems: str | None = None) -> None:
        if private_pem:
            key = serialization.load_pem_private_key(private_pem.encode(), password=None)
            if not isinstance(key, Ed25519PrivateKey):
                raise ValueError("JWT_PRIVATE_KEY must be an Ed25519 key")
            self.private = key
        else:  # dev/test only: an ephemeral key (tokens die with the process)
            self.private = Ed25519PrivateKey.generate()
        self.kid = _kid(self.private.public_key())
        self.public_keys: list[Ed25519PublicKey] = [self.private.public_key()]
        for block in (previous_public_pems or "").split("-----END PUBLIC KEY-----"):
            if "BEGIN PUBLIC KEY" in block:
                pub = serialization.load_pem_public_key((block + "-----END PUBLIC KEY-----").encode())
                if isinstance(pub, Ed25519PublicKey):
                    self.public_keys.append(pub)

    def jwks(self) -> dict[str, Any]:
        keys = []
        for pub in self.public_keys:
            jwk: dict[str, Any] = OKPAlgorithm.to_jwk(pub, as_dict=True)
            jwk.update(kid=_kid(pub), use="sig", alg="EdDSA")
            keys.append(jwk)
        return {"keys": keys}

    def sign(self, claims: dict[str, Any]) -> str:
        return jwt.encode(claims, self.private, algorithm="EdDSA", headers={"kid": self.kid})


class TokenService:
    def __init__(self, settings: Settings, keys: KeyRing, redis: Any) -> None:
        self.s = settings
        self.keys = keys
        self.redis = redis

    def _access(self, account: dict[str, Any], sid: str, mfa: bool, now: int) -> str:
        claims = {
            "iss": self.s.issuer,
            "aud": self.s.audience,
            "sub": account["id"],
            "role": account["role"],
            "email": account["email"],
            "org": account.get("organisationId"),
            "sid": sid,
            "mfa": mfa,
            "jti": ulid(),
            "iat": now,
            "exp": now + self.s.access_ttl,
        }
        return self.keys.sign(claims)

    async def _new_refresh(self, sid: str, ttl: int) -> str:
        token = "rt_" + secrets.token_urlsafe(32)
        await self.redis.set(f"rt:{_sha(token)}", sid, ex=ttl)
        return token

    async def start_session(self, account: dict[str, Any], *, mfa: bool) -> IssuedTokens:
        now = int(time.time())
        sid = ulid()
        ttl = self.s.admin_session_ttl if account["role"] == "admin" else self.s.refresh_ttl
        session = {"sub": account["id"], "exp": now + ttl, "mfa": mfa}
        await self.redis.set(f"sess:{sid}", json.dumps(session), ex=ttl)
        await self.redis.sadd(f"user_sess:{account['id']}", sid)
        await self.redis.expire(f"user_sess:{account['id']}", self.s.refresh_ttl)
        refresh = await self._new_refresh(sid, min(ttl, self.s.refresh_ttl))
        return IssuedTokens(self._access(account, sid, mfa, now), refresh, self.s.access_ttl, sid)

    async def refresh(self, refresh_token: str, load_account: Any) -> tuple[IssuedTokens, dict[str, Any]]:
        """Rotate. A reused token revokes every session of its user (TOKEN_REUSE)."""
        h = _sha(refresh_token)
        sid_raw = await self.redis.getdel(f"rt:{h}")
        if sid_raw is None:
            used_by = await self.redis.get(f"rt_used:{h}")
            if used_by is not None:
                await self.revoke_all(_s(used_by))
                raise TokenError("TOKEN_REUSE")
            raise TokenError("TOKEN_INVALID")
        sid = _s(sid_raw)
        raw = await self.redis.get(f"sess:{sid}")
        if raw is None:
            raise TokenError("SESSION_EXPIRED")
        session = json.loads(raw)
        await self.redis.set(f"rt_used:{h}", session["sub"], ex=self.s.refresh_ttl)
        account = await load_account(session["sub"])
        if account is None or account.get("status") != "ACTIVE":
            await self.revoke_session(sid)
            raise TokenError("ACCOUNT_INACTIVE")
        now = int(time.time())
        remaining = session["exp"] - now
        if remaining <= 0:
            raise TokenError("SESSION_EXPIRED")
        new_refresh = await self._new_refresh(sid, min(remaining, self.s.refresh_ttl))
        access = self._access(account, sid, bool(session.get("mfa")), now)
        return IssuedTokens(access, new_refresh, self.s.access_ttl, sid), account

    async def mark_session_mfa(self, sid: str) -> None:
        raw = await self.redis.get(f"sess:{sid}")
        if raw is not None:
            session = json.loads(raw)
            session["mfa"] = True
            ttl = max(1, session["exp"] - int(time.time()))
            await self.redis.set(f"sess:{sid}", json.dumps(session), ex=ttl)

    async def revoke_session(self, sid: str) -> None:
        await self.redis.delete(f"sess:{sid}")
        # Access tokens live 15 min; services check this key until they expire.
        await self.redis.set(f"revoked:session:{sid}", "1", ex=self.s.access_ttl + 60)

    async def revoke_all(self, sub: str, except_sid: str | None = None) -> None:
        sids = [_s(x) for x in await self.redis.smembers(f"user_sess:{sub}")]
        for sid in sids:
            if sid != except_sid:
                await self.revoke_session(sid)
                await self.redis.srem(f"user_sess:{sub}", sid)

    async def accept_totp_step(self, sub: str, step: int) -> bool:
        """Reject a TOTP code whose step was already used (replay)."""
        key = f"totp_step:{sub}"
        last = await self.redis.get(key)
        if last is not None and int(_s(last)) >= step:
            return False
        await self.redis.set(key, str(step), ex=120)
        return True

    def service_token(self, service: str) -> tuple[str, int]:
        now = int(time.time())
        claims = {
            "iss": self.s.issuer,
            "aud": self.s.audience,
            "sub": f"svc:{service}",
            "role": "service",
            "jti": ulid(),
            "iat": now,
            "exp": now + self.s.service_token_ttl,
        }
        return self.keys.sign(claims), self.s.service_token_ttl


def _s(value: Any) -> str:
    return value.decode() if isinstance(value, bytes) else str(value)
