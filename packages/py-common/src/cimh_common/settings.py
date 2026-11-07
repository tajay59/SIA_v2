"""Reading configuration that may be secret (INFRASTRUCTURE §6: Docker secrets, `*_FILE` env vars)."""

from __future__ import annotations

import os
from pathlib import Path


def env_secret(name: str, default: str | None = None) -> str:
    """`<NAME>_FILE` (path to a Docker secret) wins over `<NAME>` (dev only). Raises if neither is set."""
    value = read_secret(name)
    if value is None:
        if default is None:
            raise KeyError(f"{name} or {name}_FILE must be set")
        return default
    return value


def read_secret(name: str) -> str | None:
    path = os.environ.get(f"{name}_FILE")
    if path:
        return Path(path).read_text(encoding="utf-8").strip()
    return os.environ.get(name)
