"""Access-token verification for every service (API README §2, TR-AUTH).

Tokens are EdDSA (Ed25519) JWTs issued by identity-svc. Services verify the signature
with identity's JWKS (cached 10 min), then check the Redis revocation list.
Web clients send the token in the `access_token` cookie (+ CSRF header on writes);
mobile and service clients send `Authorization: Bearer`.
"""

from __future__ import annotations

import hmac
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal

import jwt
from fastapi import Request

from .errors import ProblemError, unauthorized

Role = Literal["admin", "staff", "user", "service"]
ROLES: tuple[Role, ...] = ("admin", "staff", "user", "service")

ACCESS_COOKIE = "access_token"
CSRF_COOKIE = "csrf_token"
CSRF_HEADER = "X-CSRF-Token"
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
CIMH_DOMAIN = "@cimh.edu.bb"


@dataclass(frozen=True)
class Principal:
    """The authenticated caller."""

    sub: str
    role: Role
    email: str = ""
    org_id: str | None = None
    jti: str = ""
    session_id: str | None = None
    claims: dict[str, Any] = field(default_factory=dict)

    @property
    def is_staff(self) -> bool:
        return self.role in ("staff", "admin")

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def is_cimh(self) -> bool:
        """@cimh.edu.bb users skip approval and cannot request items."""
        return self.email.lower().endswith(CIMH_DOMAIN)


JwksFetcher = Callable[[], Awaitable[dict[str, Any]]]
RevocationCheck = Callable[[str, str | None], Awaitable[bool]]


class JwksCache:
    """Caches identity's JWKS; refetches after `ttl` seconds or on an unknown `kid`."""

    def __init__(self, fetch: JwksFetcher, ttl: float = 600.0, clock: Callable[[], float] = time.monotonic) -> None:
        self._fetch = fetch
        self._ttl = ttl
        self._clock = clock
        self._keys: dict[str, Any] = {}
        self._loaded_at = float("-inf")

    async def _refresh(self) -> None:
        jwks = await self._fetch()
        keys: dict[str, Any] = {}
        for jwk in jwks.get("keys", []):
            if jwk.get("kty") == "OKP" and jwk.get("crv") == "Ed25519" and "kid" in jwk:
                keys[jwk["kid"]] = jwt.PyJWK(jwk, algorithm="EdDSA").key
        self._keys = keys
        self._loaded_at = self._clock()

    async def get(self, kid: str) -> Any:
        if self._clock() - self._loaded_at > self._ttl:
            await self._refresh()
        # Key rotation: an unknown kid forces one refresh, rate limited to once per 30 s.
        if kid not in self._keys and self._clock() - self._loaded_at > 30:
            await self._refresh()
        key = self._keys.get(kid)
        if key is None:
            raise unauthorized("Unknown signing key")
        return key


def http_jwks_fetcher(url: str, timeout: float = 3.0) -> JwksFetcher:
    async def fetch() -> dict[str, Any]:
        import httpx

        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
            return data

    return fetch


def redis_revocation_check(redis: Any) -> RevocationCheck:
    """Revoked if `revoked:jti:<jti>` or `revoked:session:<sid>` exists (identity-svc writes them)."""

    async def check(jti: str, session_id: str | None) -> bool:
        keys = [f"revoked:jti:{jti}"]
        if session_id:
            keys.append(f"revoked:session:{session_id}")
        return bool(await redis.exists(*keys))

    return check


class TokenVerifier:
    def __init__(
        self,
        jwks: JwksCache,
        *,
        issuer: str,
        audience: str,
        is_revoked: RevocationCheck | None = None,
        leeway: float = 30.0,
    ) -> None:
        self._jwks = jwks
        self._issuer = issuer
        self._audience = audience
        self._is_revoked = is_revoked
        self._leeway = leeway

    async def verify(self, token: str) -> Principal:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise unauthorized("Malformed token") from exc
        if header.get("alg") != "EdDSA":
            raise unauthorized("Unsupported token algorithm")
        key = await self._jwks.get(str(header.get("kid", "")))
        try:
            claims: dict[str, Any] = jwt.decode(
                token,
                key,
                algorithms=["EdDSA"],
                issuer=self._issuer,
                audience=self._audience,
                leeway=self._leeway,
                options={"require": ["exp", "iat", "sub", "jti", "role"]},
            )
        except jwt.ExpiredSignatureError as exc:
            raise unauthorized("Token expired", code="TOKEN_EXPIRED") from exc
        except jwt.PyJWTError as exc:
            raise unauthorized("Invalid token") from exc

        role = claims.get("role")
        if role not in ROLES:
            raise unauthorized("Invalid role claim")
        sid = claims.get("sid")
        if self._is_revoked is not None:
            try:
                revoked = await self._is_revoked(claims["jti"], sid)
            except Exception as exc:  # fail closed: Redis down means no access
                raise ProblemError(503, "DEPENDENCY_UNAVAILABLE", "Revocation check unavailable") from exc
            if revoked:
                raise unauthorized("Token revoked", code="TOKEN_REVOKED")
        return Principal(
            sub=str(claims["sub"]),
            role=role,
            email=str(claims.get("email", "")),
            org_id=claims.get("org"),
            jti=str(claims["jti"]),
            session_id=sid,
            claims=claims,
        )


def extract_token(request: Request) -> tuple[str | None, bool]:
    """Return (token, from_cookie). Bearer wins over cookie."""
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() or None, False
    cookie = request.cookies.get(ACCESS_COOKIE)
    return (cookie or None), True


def check_csrf(request: Request) -> None:
    """Double-submit check for cookie-authenticated writes."""
    if request.method not in UNSAFE_METHODS:
        return
    cookie = request.cookies.get(CSRF_COOKIE, "")
    header = request.headers.get(CSRF_HEADER, "")
    if not cookie or not header or not hmac.compare_digest(cookie, header):
        raise ProblemError(403, "CSRF_FAILED", "Missing or invalid CSRF token")
