from __future__ import annotations

import json
import logging

from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict

from cimh_common.app import create_app
from cimh_common.errors import ProblemError, conflict
from cimh_common.ids import new_id, ulid, ulid_timestamp_ms
from cimh_common.logging import JsonFormatter


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid")
    qty: int


def client(checks: dict | None = None) -> TestClient:  # type: ignore[type-arg]
    app = create_app("t", readiness_checks=checks, configure_logs=False)

    @app.post("/thing")
    async def thing(body: Body) -> dict[str, int]:
        return {"qty": body.qty}

    @app.get("/conflict")
    async def c() -> None:
        raise conflict("VERSION_CONFLICT", "stale")

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("secret internals")

    return TestClient(app, raise_server_exceptions=False)


def test_health_and_metrics() -> None:
    c = client()
    assert c.get("/health/live").json() == {"status": "ok"}
    assert c.get("/health/ready").status_code == 200
    m = c.get("/metrics").text
    assert "http_requests_total" in m


def test_ready_fails_when_check_fails() -> None:
    async def bad() -> bool:
        return False

    async def raises() -> bool:
        raise OSError

    r = client({"mongo": bad, "redis": raises}).get("/health/ready")
    assert r.status_code == 503
    assert r.json()["checks"] == {"mongo": "fail", "redis": "fail"}


def test_validation_is_422_problem_and_rejects_unknown_fields() -> None:
    r = client().post("/thing", json={"qty": 1, "extra": True})
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == "VALIDATION_FAILED"
    assert any(e["field"] == "extra" for e in body["errors"])


def test_problem_error_and_trace_header() -> None:
    r = client().get("/conflict", headers={"traceparent": "00-" + "a" * 32 + "-" + "b" * 16 + "-01"})
    assert r.status_code == 409
    assert r.json()["code"] == "VERSION_CONFLICT"
    assert r.headers["X-Trace-Id"] == "a" * 32
    assert r.headers["X-Content-Type-Options"] == "nosniff"


def test_unhandled_error_hides_details() -> None:
    r = client().get("/boom")
    assert r.status_code == 500
    assert "secret" not in r.text


def test_404_is_problem() -> None:
    r = client().get("/nope")
    assert r.status_code == 404
    assert r.json()["status"] == 404


def test_ulid_sortable_and_prefixed_ids() -> None:
    a, b = ulid(1_000), ulid(2_000)
    assert len(a) == 26
    assert a < b
    assert ulid_timestamp_ms(b) == 2_000
    assert new_id("ORD").startswith("ORD")
    assert len(new_id("ORD")) == 29
    try:
        new_id("XXX")
    except ValueError:
        pass
    else:
        raise AssertionError


def test_problem_error_defaults() -> None:
    e = ProblemError(403, "CIMH_CANNOT_REQUEST")
    assert e.title == "Forbidden"
    assert e.type_path == "cimh-cannot-request"


def test_json_log_redacts_secrets() -> None:
    rec = logging.LogRecord("x", logging.INFO, "f", 1, "hello", (), None)
    rec.password = "hunter2"
    rec.ctx = {"refresh_token": "abc", "orderId": "ORD1"}
    out = json.loads(JsonFormatter("svc").format(rec))
    assert out["password"] == "[REDACTED]"
    assert out["ctx"] == {"refresh_token": "[REDACTED]", "orderId": "ORD1"}
    assert out["service"] == "svc"
