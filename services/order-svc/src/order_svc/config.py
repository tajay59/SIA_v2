"""order-svc settings from the environment. Secrets come from `*_FILE` (Docker secrets)."""

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
    # Sync HTTP (TAD §4.5): catalog (product snapshots, admin fee), inventory (availability, picks),
    # identity (account summary at submission, file-access checks). Service token from identity-svc.
    identity_url: str | None = None
    catalog_url: str | None = None
    inventory_url: str | None = None
    service_secret: str | None = None
    quote_valid_days: int = 30

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
            inventory_url=env("INVENTORY_URL"),
            service_secret=read_secret("SERVICE_SECRET"),
            quote_valid_days=int(env("QUOTE_VALID_DAYS", str(cls.quote_valid_days))),
        )
