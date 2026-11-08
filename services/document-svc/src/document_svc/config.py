"""document-svc settings from the environment. Secrets come from `*_FILE` (Docker secrets)."""

from __future__ import annotations

import os
from dataclasses import dataclass

from cimh_common.settings import read_secret

MB = 1024 * 1024


def _flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    return default if raw is None else raw.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    redis_url: str | None = None
    jwks_url: str | None = None
    issuer: str = "https://identity.cimh.internal"
    audience: str = "cimh-stores"
    # Sync HTTP (TAD §4.5): order-svc answers "may this user see/act on this request?" and gives the staff view
    # the PDFs are rendered from. Service token from identity-svc.
    identity_url: str | None = None
    order_url: str | None = None
    service_secret: str | None = None
    kafka_bootstrap: str | None = None
    data_dir: str = "/srv/sia-data"
    max_bytes: int = 20 * MB
    # ClamAV (TR-SEC-6). Production scans every upload and fails closed. Staging-lite has no memory for clamd
    # (owner decision 2026-11-08), so it runs with SCAN_ENABLED=false.
    scan_enabled: bool = True
    clamd_host: str = "clamav"
    clamd_port: int = 3310
    # Dev only: no nginx in front, so the service streams the bytes itself instead of X-Accel-Redirect.
    serve_direct: bool = False

    @classmethod
    def from_env(cls) -> Settings:
        env = os.environ.get
        return cls(
            redis_url=read_secret("REDIS_URL"),
            jwks_url=env("JWKS_URL"),
            issuer=env("JWT_ISSUER", cls.issuer),
            audience=env("JWT_AUDIENCE", cls.audience),
            identity_url=env("IDENTITY_URL"),
            order_url=env("ORDER_URL"),
            service_secret=read_secret("SERVICE_SECRET"),
            kafka_bootstrap=env("KAFKA_BOOTSTRAP"),
            data_dir=env("DATA_DIR", cls.data_dir),
            max_bytes=int(env("MAX_UPLOAD_MB", "20")) * MB,
            scan_enabled=_flag("SCAN_ENABLED", True),
            clamd_host=env("CLAMD_HOST", cls.clamd_host),
            clamd_port=int(env("CLAMD_PORT", str(cls.clamd_port))),
            serve_direct=_flag("SERVE_DIRECT", False),
        )
