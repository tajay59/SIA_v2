"""Settings from the environment. Secrets come from files (Docker secrets), never from env values in git."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _read_secret(name: str) -> str | None:
    """`<NAME>_FILE` (Docker secret path) wins over `<NAME>` (dev only)."""
    path = os.environ.get(f"{name}_FILE")
    if path:
        return Path(path).read_text(encoding="utf-8").strip()
    return os.environ.get(name)


def _service_secrets() -> dict[str, str]:
    """SERVICE_SECRETS_FILE holds lines `catalog=<secret>`; one per calling service."""
    raw = _read_secret("SERVICE_SECRETS") or ""
    out = {}
    for line in raw.replace(",", "\n").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


@dataclass(frozen=True)
class Settings:
    issuer: str = "https://identity.cimh.internal"
    audience: str = "cimh-stores"
    access_ttl: int = 15 * 60
    refresh_ttl: int = 7 * 24 * 3600
    admin_session_ttl: int = 8 * 3600
    service_token_ttl: int = 5 * 60
    code_ttl: int = 15 * 60
    code_max_attempts: int = 5
    code_max_sends_per_hour: int = 3
    lockout_threshold: int = 5
    lockout_base_seconds: int = 15 * 60
    password_min_length: int = 12
    cookie_secure: bool = True
    cookie_domain: str | None = None
    private_key_pem: str | None = None
    previous_public_keys_pem: str | None = None
    data_key_b64: str | None = None  # 32-byte AES-GCM key for TOTP secrets and code envelopes
    code_pepper: str = "dev-pepper-change-me"
    service_secrets: dict[str, str] = field(default_factory=dict)
    hibp_enabled: bool = True
    mongo_url: str | None = None
    redis_url: str | None = None
    db_name: str = "inventory"

    @classmethod
    def from_env(cls) -> Settings:
        env = os.environ.get
        settings = cls(
            issuer=env("JWT_ISSUER", cls.issuer),
            audience=env("JWT_AUDIENCE", cls.audience),
            cookie_secure=env("COOKIE_SECURE", "true").lower() != "false",
            cookie_domain=env("COOKIE_DOMAIN") or None,
            private_key_pem=_read_secret("JWT_PRIVATE_KEY"),
            previous_public_keys_pem=_read_secret("JWT_PREVIOUS_PUBLIC_KEYS"),
            data_key_b64=_read_secret("DATA_KEY"),
            code_pepper=_read_secret("CODE_PEPPER") or cls.code_pepper,
            service_secrets=_service_secrets(),
            hibp_enabled=env("HIBP_ENABLED", "true").lower() != "false",
            mongo_url=_read_secret("MONGO_URL"),
            redis_url=_read_secret("REDIS_URL"),
            db_name=env("MONGO_DB", cls.db_name),
        )
        settings.require_keys(allow_ephemeral=env("ALLOW_EPHEMERAL_KEYS", "false").lower() == "true")
        return settings

    def require_keys(self, *, allow_ephemeral: bool) -> None:
        """Without a configured JWT key and data key, every worker process would invent its own: tokens
        signed by one worker fail on another, and codes sealed by one can't be opened by another. Only a
        single-worker dev process may run with throw-away keys (ALLOW_EPHEMERAL_KEYS=true)."""
        missing = [n for n, v in (("JWT_PRIVATE_KEY", self.private_key_pem), ("DATA_KEY", self.data_key_b64)) if not v]
        if missing and not allow_ephemeral:
            names = ", ".join(missing)
            raise RuntimeError(f"{names} not configured (set *_FILE); refusing to start with per-process keys")
