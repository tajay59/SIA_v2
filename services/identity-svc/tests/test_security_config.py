"""Security primitives, key loading and settings."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import os
from pathlib import Path
from typing import Any

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from identity_svc import security as sec
from identity_svc.config import Settings
from identity_svc.tokens import KeyRing


def test_argon2_roundtrip_and_unknown_hash() -> None:
    h = sec.hash_password("long enough password")
    assert sec.verify_password(h, "long enough password")
    assert not sec.verify_password(h, "wrong")
    assert not sec.verify_password(None, "anything")
    assert not sec.verify_password("not-a-hash", "x")
    assert not sec.needs_rehash(h)


@pytest.mark.parametrize(
    ("stored", "ok"),
    [
        ("pbkdf2:sha256:1000$salt$" + hashlib.pbkdf2_hmac("sha256", b"pw", b"salt", 1000).hex(), True),
        ("pbkdf2:sha512:1000$salt$" + hashlib.pbkdf2_hmac("sha512", b"pw", b"salt", 1000).hex(), True),
        ("pbkdf2:sha256:1000$salt$deadbeef", False),
        ("scrypt:32768:8:1$salt$abc", False),
        ("garbage", False),
        ("pbkdf2:sha256:notanint$s$x", False),
    ],
)
def test_legacy_werkzeug(stored: str, ok: bool) -> None:
    assert sec.verify_legacy_werkzeug(stored, "pw") is ok


def test_codes() -> None:
    c = sec.new_code()
    assert len(c) == 6
    assert c.isdigit()
    h = sec.hash_code(c, "pepper")
    assert sec.code_matches(c, h, "pepper")
    assert not sec.code_matches(c, h, "other-pepper")


def test_envelope_binds_context() -> None:
    key = base64.b64encode(os.urandom(32)).decode()
    env = sec.Envelope(key)
    sealed = env.seal("123456", "TMP1")
    assert env.open(sealed, "TMP1") == "123456"
    with pytest.raises(Exception):  # noqa: B017, PT011 - any crypto failure
        env.open(sealed, "TMP2")  # can't move a sealed value to another record
    with pytest.raises(ValueError, match="32 bytes"):
        sec.Envelope(base64.b64encode(b"short").decode())


def test_totp_known_vector() -> None:
    # RFC 6238 test secret "12345678901234567890" (SHA-1), T=59 -> 94287082 (8 digits) -> 287082
    secret = base64.b32encode(b"12345678901234567890").decode()
    assert sec.totp_now(secret, 59) == "287082"
    assert sec.totp_verify(secret, "287082", at=59) == 1
    assert sec.totp_verify(secret, "287082", at=59 + 90) is None
    assert "secret=" in sec.otpauth_uri(secret, "a@b.c")


def test_hibp_found_not_found_and_fail_open(monkeypatch: pytest.MonkeyPatch) -> None:
    sha = hashlib.sha1(b"hunter2hunter2", usedforsecurity=False).hexdigest().upper()
    real = httpx.AsyncClient

    def client_with(handler: Any) -> Any:
        return lambda **kw: real(transport=httpx.MockTransport(handler), **kw)

    def found(req: httpx.Request) -> httpx.Response:
        assert req.url.path.endswith(sha[:5])  # only the prefix leaves the service
        return httpx.Response(200, text=f"0000000000000000000000000000000000A:0\n{sha[5:]}:42\n")

    monkeypatch.setattr(httpx, "AsyncClient", client_with(found))
    assert asyncio.run(sec.hibp_check()("hunter2hunter2")) is True

    monkeypatch.setattr(httpx, "AsyncClient", client_with(lambda r: httpx.Response(200, text="ABC:1\n")))
    assert asyncio.run(sec.hibp_check()("hunter2hunter2")) is False

    monkeypatch.setattr(httpx, "AsyncClient", client_with(lambda r: httpx.Response(503)))
    assert asyncio.run(sec.hibp_check()("hunter2hunter2")) is False  # fail open (TRD §8)
    assert asyncio.run(sec.no_breach_check("x")) is False


def _pem(key: Ed25519PrivateKey) -> str:
    return key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()


def test_keyring_from_pem_with_previous_key() -> None:
    old, new = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
    old_pub = old.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    ring = KeyRing(_pem(new), old_pub.decode())
    jwks = ring.jwks()["keys"]
    assert len(jwks) == 2  # rotation: old tokens stay verifiable
    assert jwks[0]["kid"] == ring.kid
    from cryptography.hazmat.primitives.asymmetric.ec import SECP256R1, generate_private_key

    ec = generate_private_key(SECP256R1()).private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    with pytest.raises(ValueError, match="Ed25519"):
        KeyRing(ec.decode())


def test_settings_from_env_reads_secret_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "svc").write_text("catalog=c1\norder = o1\n")
    (tmp_path / "pepper").write_text("p3pp3r\n")
    monkeypatch.setenv("SERVICE_SECRETS_FILE", str(tmp_path / "svc"))
    monkeypatch.setenv("CODE_PEPPER_FILE", str(tmp_path / "pepper"))
    monkeypatch.setenv("COOKIE_SECURE", "false")
    monkeypatch.setenv("HIBP_ENABLED", "false")
    monkeypatch.setenv("JWT_ISSUER", "https://id.test")
    s = Settings.from_env()
    assert s.service_secrets == {"catalog": "c1", "order": "o1"}
    assert s.code_pepper == "p3pp3r"
    assert s.cookie_secure is False
    assert s.hibp_enabled is False
    assert s.issuer == "https://id.test"


def test_build_app_requires_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    from identity_svc.main import build_app

    with pytest.raises(RuntimeError, match="MONGO_URL"):
        build_app(Settings())
    with pytest.raises(RuntimeError, match="REDIS_URL"):
        build_app(Settings(mongo_url="mongodb://127.0.0.1:1"))
