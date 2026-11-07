"""ULIDs (event ids, idempotency keys) and prefixed entity ids (USR…, ORG…, ORD…)."""

from __future__ import annotations

import os
import time

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # Crockford base32

ENTITY_PREFIXES = frozenset({"USR", "ORG", "ORD", "CRT", "QTE", "FIL"})


def ulid(timestamp_ms: int | None = None) -> str:
    """26-char ULID: 48-bit ms timestamp + 80 random bits; sorts by creation time."""
    ts = int(time.time() * 1000) if timestamp_ms is None else timestamp_ms
    if not 0 <= ts < 2**48:
        raise ValueError("timestamp out of range")
    value = (ts << 80) | int.from_bytes(os.urandom(10), "big")
    chars = []
    for _ in range(26):
        chars.append(_ALPHABET[value & 31])
        value >>= 5
    return "".join(reversed(chars))


def ulid_timestamp_ms(value: str) -> int:
    n = 0
    for ch in value[:10]:
        n = n * 32 + _ALPHABET.index(ch)
    return n


def new_id(prefix: str) -> str:
    """Prefixed id, e.g. new_id("ORD") -> "ORD01J…". Products/units/shelves keep legacy barcodes."""
    if prefix not in ENTITY_PREFIXES:
        raise ValueError(f"unknown id prefix {prefix!r}")
    return prefix + ulid()
