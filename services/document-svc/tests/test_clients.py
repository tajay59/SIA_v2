"""document-svc → order-svc over HTTP (HttpOrders): service token, 404 → None, order-svc's own refusals passed on
unchanged (the invoice calls: INVOICE_EXISTS, INVOICE_NUMBER_TAKEN, INVOICE_LOCKED, VERSION_CONFLICT), anything else
503."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import pytest

from cimh_common.errors import ProblemError
from document_svc.clients import HttpOrders

ORDERS = "http://order:8000/api/orders/v1/internal"


class Fake:
    """Identity hands out a service token; order-svc answers from a table of (method, path) -> (status, body)."""

    def __init__(self, answers: dict[tuple[str, str], tuple[int, Any]]) -> None:
        self.answers = answers
        self.seen: list[httpx.Request] = []
        self.tokens = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/internal/service-token"):
            self.tokens += 1
            return httpx.Response(200, json={"token": "svc-token", "expiresIn": 300})
        self.seen.append(request)
        status, body = self.answers.get((request.method, request.url.path), (404, {"code": "NOT_FOUND"}))
        return httpx.Response(status, json=body)


def client(fake: Fake) -> HttpOrders:
    return HttpOrders(identity_url="http://identity:8000", order_url="http://order:8000", secret="s",
                      transport=httpx.MockTransport(fake))  # fmt: skip


def run(coro: Any) -> Any:
    return asyncio.run(coro)


REC = {"rev": None, "number": "1", "date": "2026-11-24", "lines": [], "by": {}, "file": {}}


def test_reads_with_one_service_token_and_404_is_none() -> None:
    fake = Fake({
        ("GET", "/api/orders/v1/internal/requests/ORD1"): (200, {"id": "ORD1"}),
        ("GET", "/api/orders/v1/internal/requests/ORD1/access"): (200, {"allowed": True}),
        ("GET", "/api/orders/v1/internal/invoice-numbers/next"): (200, {"number": "INV-2"}),
    })  # fmt: skip
    orders = client(fake)

    async def go() -> None:
        assert await orders.request("ORD1") == {"id": "ORD1"}
        assert await orders.access("ORD1", "USR1") == {"allowed": True}
        assert await orders.request("ORDnope") is None
        assert await orders.next_invoice_number("invoice") == "INV-2"

    run(go())
    assert fake.tokens == 1  # cached between calls
    assert all(r.headers["Authorization"] == "Bearer svc-token" for r in fake.seen)
    assert fake.seen[1].url.params["user"] == "USR1"
    assert fake.seen[-1].url.params["kind"] == "invoice"


def test_next_number_none_when_order_svc_has_none() -> None:
    fake = Fake({("GET", "/api/orders/v1/internal/invoice-numbers/next"): (200, {"number": None})})
    assert run(client(fake).next_invoice_number("commercial_invoice")) is None


def test_attach_sends_the_file_fields_only() -> None:
    fake = Fake({("POST", "/api/orders/v1/internal/requests/ORD1/files"): (204, None)})
    meta = {"id": "FIL1", "kind": "invoice", "name": "I.pdf", "mime": "application/pdf", "size": 9, "sha256": "x",
            "quoteVersion": 2, "uploadedBy": {"id": "u"}}  # fmt: skip
    run(client(fake).attach("ORD1", meta))
    assert json.loads(fake.seen[0].content) == {"id": "FIL1", "kind": "invoice", "name": "I.pdf",
                                                "mime": "application/pdf", "size": 9, "quoteVersion": 2}  # fmt: skip


@pytest.mark.parametrize(
    ("status", "code"),
    [(409, "INVOICE_EXISTS"), (409, "INVOICE_NUMBER_TAKEN"), (409, "INVOICE_LOCKED"), (409, "VERSION_CONFLICT"),
     (403, "FORBIDDEN"), (422, "VALIDATION_FAILED")],
)  # fmt: skip
def test_invoice_refusals_are_passed_on_unchanged(status: int, code: str) -> None:
    path = "/api/orders/v1/internal/requests/ORD1/invoices/invoice"
    body = {"code": code, "detail": f"because {code}", "errors": [{"field": "number", "message": "used"}, "junk"]}
    fake = Fake({("PUT", path): (status, body)})
    with pytest.raises(ProblemError) as err:
        run(client(fake).record_invoice("ORD1", "invoice", REC))
    assert (err.value.status, err.value.code, err.value.detail) == (status, code, f"because {code}")
    assert err.value.errors == [{"field": "number", "message": "used"}]  # non-objects dropped


def test_invoice_record_and_void() -> None:
    base = "/api/orders/v1/internal/requests/ORD1/invoices/commercial_invoice"
    fake = Fake({
        ("PUT", base): (200, {"invoice": {"rev": 1}, "replacedFileId": None}),
        ("POST", base + "/void"): (200, {"voidedFileId": "FIL1", "number": "C-1", "rev": 1}),
    })  # fmt: skip
    orders = client(fake)
    assert run(orders.record_invoice("ORD1", "commercial_invoice", REC))["invoice"] == {"rev": 1}
    assert run(orders.void_invoice("ORD1", "commercial_invoice", {"rev": 1}))["voidedFileId"] == "FIL1"


def test_invoice_calls_on_a_missing_request_are_404() -> None:
    orders = client(Fake({}))
    for call in (orders.record_invoice("ORDx", "invoice", REC), orders.void_invoice("ORDx", "invoice", {"rev": 1})):
        with pytest.raises(ProblemError) as err:
            run(call)
        assert err.value.status == 404


def test_quote_preview_passes_409_and_422_on() -> None:
    path = "/api/orders/v1/internal/requests/ORD1/quote-preview"
    fake = Fake({("GET", path): (422, {"code": "SHIPPING_ESTIMATE_REQUIRED", "detail": "Shipping for Vaisala"})})
    with pytest.raises(ProblemError) as err:
        run(client(fake).quote_preview("ORD1"))
    assert err.value.code == "SHIPPING_ESTIMATE_REQUIRED"


def test_other_failures_are_503() -> None:
    fake = Fake({("GET", "/api/orders/v1/internal/requests/ORD1"): (500, {"detail": "boom"})})
    with pytest.raises(ProblemError) as err:
        run(client(fake).request("ORD1"))
    assert err.value.status == 503

    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    orders = HttpOrders(identity_url="http://identity:8000", order_url="http://order:8000", secret="s",
                        transport=httpx.MockTransport(down))  # fmt: skip
    with pytest.raises(ProblemError) as err:
        run(orders.request("ORD1"))
    assert err.value.status == 503


def test_a_relayed_problem_without_json_still_carries_the_status() -> None:
    def text(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/internal/service-token"):
            return httpx.Response(200, json={"token": "t"})
        return httpx.Response(409, text="not json")

    orders = HttpOrders(identity_url="http://identity:8000", order_url="http://order:8000", secret="s",
                        transport=httpx.MockTransport(text))  # fmt: skip
    with pytest.raises(ProblemError) as err:
        run(orders.record_invoice("ORD1", "invoice", REC))
    assert err.value.status == 409
    assert err.value.code is None
