"""inventory-svc settings from the environment. Secrets come from `*_FILE` (Docker secrets)."""

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
    # Sites, locations and shelves live in `misc` (catalog-svc): read/written through catalog's internal API
    # with a service token from identity-svc (TAD §4.3 design note), cached in Redis.
    identity_url: str | None = None
    catalog_url: str | None = None
    document_url: str | None = None  # optional: label PDFs
    service_secret: str | None = None
    place_cache_seconds: int = 600

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
            catalog_url=env("CATALOG_URL"),
            document_url=env("DOCUMENT_URL"),
            service_secret=read_secret("SERVICE_SECRET"),
            place_cache_seconds=int(env("PLACE_CACHE_SECONDS", str(cls.place_cache_seconds))),
        )
