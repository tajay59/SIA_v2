"""Cursor paging (API README §1): `?limit=` (<= 100, default 25) & `?cursor=`; responses
`{items, nextCursor}`. The cursor is an opaque base64 of the last item's (sort value, id)."""

from __future__ import annotations

import base64
import json
from datetime import datetime
from typing import Any

from .errors import ProblemError

DEFAULT_LIMIT = 25
MAX_LIMIT = 100


def clamp_limit(limit: int | None) -> int:
    if limit is None:
        return DEFAULT_LIMIT
    if limit < 1 or limit > MAX_LIMIT:
        raise ProblemError(422, "VALIDATION_FAILED", f"limit must be 1..{MAX_LIMIT}")
    return limit


def encode_cursor(sort_value: Any, item_id: str) -> str:
    v = {"$dt": sort_value.isoformat()} if isinstance(sort_value, datetime) else sort_value
    return base64.urlsafe_b64encode(json.dumps([v, item_id]).encode()).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[Any, str]:
    try:
        raw = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
        value, item_id = raw
        if isinstance(value, dict) and "$dt" in value:
            value = datetime.fromisoformat(value["$dt"])
        return value, str(item_id)
    except Exception as exc:
        raise ProblemError(422, "VALIDATION_FAILED", "invalid cursor") from exc


def after_cursor(field: str, cursor: str | None, descending: bool = False) -> dict[str, Any]:
    """Mongo filter for items strictly after the cursor in (field, id) order."""
    if not cursor:
        return {}
    value, item_id = decode_cursor(cursor)
    op = "$lt" if descending else "$gt"
    return {"$or": [{field: {op: value}}, {field: value, "id": {op: item_id}}]}


async def page(
    collection: Any,
    filter: dict[str, Any],
    *,
    sort_field: str,
    cursor: str | None,
    limit: int | None,
    descending: bool = False,
) -> tuple[list[dict[str, Any]], str | None]:
    n = clamp_limit(limit)
    query = dict(filter)
    after = after_cursor(sort_field, cursor, descending)
    if after:
        query = {"$and": [query, after]} if query else after
    direction = -1 if descending else 1
    docs = await collection.find(query).sort([(sort_field, direction), ("id", direction)]).limit(n + 1).to_list()
    next_cursor = None
    if len(docs) > n:
        docs = docs[:n]
        last = docs[-1]
        next_cursor = encode_cursor(last.get(sort_field), last["id"])
    return docs, next_cursor
