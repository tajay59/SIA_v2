"""Passwords (Argon2id + legacy Werkzeug upgrade), breached-password check, one-time codes,
TOTP (RFC 6238) and AES-GCM envelopes for secrets at rest."""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import secrets
import struct
import time
from collections.abc import Awaitable, Callable

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

log = logging.getLogger(__name__)

# OWASP-recommended Argon2id parameters (m=19 MiB is the floor; we use 64 MiB, t=3, p=4).
_hasher = PasswordHasher(time_cost=3, memory_cost=64 * 1024, parallelism=4)
_DUMMY_HASH = _hasher.hash("dummy-password-for-timing")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(stored_hash: str | None, password: str) -> bool:
    """Constant-ish time: an unknown account still costs one Argon2 verification."""
    try:
        return _hasher.verify(stored_hash or _DUMMY_HASH, password) and stored_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(stored_hash: str) -> bool:
    return _hasher.check_needs_rehash(stored_hash)


def verify_legacy_werkzeug(stored: str, password: str) -> bool:
    """Legacy SIA hashes: `pbkdf2:sha256:<iterations>$<salt>$<hex>` (Werkzeug). Anything else fails."""
    try:
        method, salt, expected = stored.split("$", 2)
        algo, digest, *rest = method.split(":")
        if algo != "pbkdf2" or digest not in ("sha256", "sha512"):
            return False
        iterations = int(rest[0]) if rest else 600_000
        got = hashlib.pbkdf2_hmac(digest, password.encode(), salt.encode(), iterations).hex()
        return hmac.compare_digest(got, expected)
    except (ValueError, IndexError):
        return False


# ---- breached passwords (TR-AUTH-7; fail open per TRD §8) ----

BreachCheck = Callable[[str], Awaitable[bool]]


def hibp_check(timeout: float = 2.0) -> BreachCheck:
    async def check(password: str) -> bool:
        import httpx

        # HIBP k-anonymity protocol is defined over SHA-1; not used for any security property.
        sha1 = hashlib.sha1(password.encode(), usedforsecurity=False).hexdigest().upper()  # nosemgrep
        prefix, suffix = sha1[:5], sha1[5:]
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(
                    f"https://api.pwnedpasswords.com/range/{prefix}", headers={"Add-Padding": "true"}
                )
                resp.raise_for_status()
        except Exception:
            log.warning("breached-password check unavailable; continuing without it")
            return False
        for line in resp.text.splitlines():
            h, _, count = line.partition(":")
            if h == suffix and count.strip() != "0":
                return True
        return False

    return check


async def no_breach_check(password: str) -> bool:
    return False


# ---- one-time codes (TR-AUTH-8) ----


def new_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_code(code: str, pepper: str) -> str:
    return hmac.new(pepper.encode(), code.encode(), hashlib.sha256).hexdigest()


def code_matches(code: str, stored_hash: str, pepper: str) -> bool:
    return hmac.compare_digest(hash_code(code, pepper), stored_hash)


# ---- AES-GCM envelopes (TOTP secrets, codes awaiting delivery) ----


class Envelope:
    def __init__(self, key_b64: str | None) -> None:
        key = base64.b64decode(key_b64) if key_b64 else AESGCM.generate_key(bit_length=256)
        if len(key) != 32:
            raise ValueError("DATA_KEY must be 32 bytes (base64)")
        self._aead = AESGCM(key)

    def seal(self, plaintext: str, context: str) -> str:
        nonce = os.urandom(12)
        ct = self._aead.encrypt(nonce, plaintext.encode(), context.encode())
        return base64.b64encode(nonce + ct).decode()

    def open(self, sealed: str, context: str) -> str:
        raw = base64.b64decode(sealed)
        return self._aead.decrypt(raw[:12], raw[12:], context.encode()).decode()


# ---- TOTP (RFC 6238, SHA-1, 30 s, 6 digits) ----


def new_totp_secret() -> str:
    return base64.b32encode(os.urandom(20)).decode().rstrip("=")


def _hotp(secret_b32: str, counter: int) -> str:
    key = base64.b32decode(secret_b32 + "=" * (-len(secret_b32) % 8))
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return f"{value % 1_000_000:06d}"


def totp_now(secret_b32: str, at: float | None = None) -> str:
    return _hotp(secret_b32, int((at if at is not None else time.time()) // 30))


def totp_verify(secret_b32: str, code: str, at: float | None = None, window: int = 1) -> int | None:
    """Return the matching time step (for replay protection) or None."""
    step = int((at if at is not None else time.time()) // 30)
    for s in range(step - window, step + window + 1):
        if hmac.compare_digest(_hotp(secret_b32, s), code):
            return s
    return None


def otpauth_uri(secret_b32: str, email: str, issuer: str = "CIMH Stores") -> str:
    from urllib.parse import quote

    return (
        f"otpauth://totp/{quote(issuer)}:{quote(email)}?secret={secret_b32}"
        f"&issuer={quote(issuer)}&algorithm=SHA1&digits=6&period=30"
    )
