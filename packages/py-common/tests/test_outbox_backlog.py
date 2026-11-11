"""Outbox backlog gauges (alert OutboxBacklog, TEST_STRATEGY §7 "Outbox relay down")."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient

from cimh_common.app import create_app
from cimh_common.outbox import outbox_backlog_hook

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)


class Cursor:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    async def to_list(self, _n: int) -> list[dict[str, Any]]:
        return self.rows


class Coll:
    def __init__(self, rows: list[dict[str, Any]] | Exception) -> None:
        self.rows = rows
        self.pipelines: list[Any] = []

    async def aggregate(self, pipeline: list[Any], **_: Any) -> Cursor:
        self.pipelines.append(pipeline)
        if isinstance(self.rows, Exception):
            raise self.rows
        return Cursor(self.rows)


def scrape(collections: dict[str, Coll]) -> str:
    app = create_app("test-svc", configure_logs=False)
    app.state.metrics.scrape_hooks.append(outbox_backlog_hook(app.state.metrics, collections, now=lambda: NOW))
    with TestClient(app) as c:
        r = c.get("/metrics")
    assert r.status_code == 200
    return r.text


def test_pending_events_and_oldest_age() -> None:
    orders = Coll([{"_id": None, "n": 3, "t": NOW - timedelta(minutes=10)}])
    text = scrape({"orders": orders})
    assert 'outbox_pending_events{collection="orders",service="test-svc"} 3.0' in text
    assert 'outbox_oldest_event_age_seconds{collection="orders",service="test-svc"} 600.0' in text
    assert orders.pipelines[0][0] == {"$match": {"outbox.0": {"$exists": True}}}  # uses the sparse index


def test_empty_outbox_reports_zero_and_naive_dates_are_utc() -> None:
    naive = (NOW - timedelta(seconds=30)).replace(tzinfo=None)
    text = scrape({"product": Coll([]), "misc": Coll([{"_id": None, "n": 1, "t": naive}])})
    assert 'outbox_pending_events{collection="product",service="test-svc"} 0.0' in text
    assert 'outbox_oldest_event_age_seconds{collection="misc",service="test-svc"} 30.0' in text


def test_a_failing_database_never_breaks_metrics() -> None:
    text = scrape({"orders": Coll(TimeoutError("mongo down"))})
    assert "http_requests_total" in text or "outbox_pending_events" in text


def test_hook_is_plain_async() -> None:
    class M:
        service = "s"

        class G:
            def __init__(self) -> None:
                self.v: dict[tuple[str, str], float] = {}

            def labels(self, *k: str) -> Any:
                g = self

                class S:
                    def set(self, v: float) -> None:
                        g.v[k] = v

                return S()

        outbox_pending = G()
        outbox_oldest = G()

    m = M()
    asyncio.run(outbox_backlog_hook(m, {"stock": Coll([])})())
    assert m.outbox_pending.v == {("s", "stock"): 0}
