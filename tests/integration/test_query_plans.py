"""Integration: every catalog-svc read uses an index (TRD TR-DATA-5).

Seeds 20k synthetic products (tools/perf/seed_catalog.py) into a fresh database on the real MongoDB, lets the
service create its indexes, calls every read path through tools/perf/explain_catalog.py and explains the
queries it issued. Any collection scan, in-memory sort (other than `$text` ranking) or unselective plan fails.
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.integration
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools" / "perf"))


@pytest.mark.req("TR-DATA-5")
def test_catalog_reads_use_indexes(stack: Any) -> None:
    from explain_catalog import collect
    from pymongo import AsyncMongoClient
    from querylog import explain_all, report
    from seed_catalog import generate

    from catalog_svc.store import Store

    async def go() -> list[Any]:
        client: AsyncMongoClient[dict[str, Any]] = AsyncMongoClient(stack.mongo_url, tz_aware=True)
        name = f"itest_plans_{uuid.uuid4().hex[:8]}"
        db = client[name]
        try:
            await db.product.insert_many(list(generate(7, 20_000)))
            await Store(db).ensure_indexes()
            return await explain_all(db, await collect(db))
        finally:
            await client.drop_database(name)
            await client.close()

    graded = asyncio.run(go())
    assert len(graded) > 40
    bad = [g for g in graded if g.grade != "OK"]
    assert not bad, "\n" + report(bad)
