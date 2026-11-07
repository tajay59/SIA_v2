"""catalog-svc settings from the environment. Secrets come from `*_FILE` (Docker secrets)."""

from __future__ import annotations

import os
from dataclasses import dataclass

from cimh_common.settings import read_secret


@dataclass(frozen=True)
class Settings:
    mongo_url: str | None = None
    redis_url: str | None = None
    db_name: str = "inventory"
    jwks_url: str | None = None
    issuer: str = "https://identity.cimh.internal"
    audience: str = "cimh-stores"
    # identity-svc internal API: checks that email-list members are staff/admin accounts.
    identity_url: str | None = None
    service_secret: str | None = None
    # Files volume (INFRASTRUCTURE §5): originals wait in incoming/, media-worker writes products/.
    media_root: str = "/srv/sia-data"
    media_url_prefix: str = "/media/products/"
    max_image_bytes: int = 20 * 1024 * 1024
    max_images_per_upload: int = 10

    @classmethod
    def from_env(cls) -> Settings:
        env = os.environ.get
        return cls(
            mongo_url=read_secret("MONGO_URL"),
            redis_url=read_secret("REDIS_URL"),
            db_name=env("MONGO_DB", cls.db_name),
            jwks_url=env("JWKS_URL"),
            issuer=env("JWT_ISSUER", cls.issuer),
            audience=env("JWT_AUDIENCE", cls.audience),
            identity_url=env("IDENTITY_URL"),
            service_secret=read_secret("SERVICE_SECRET"),
            media_root=env("MEDIA_ROOT", cls.media_root),
            media_url_prefix=env("MEDIA_URL_PREFIX", cls.media_url_prefix),
        )
