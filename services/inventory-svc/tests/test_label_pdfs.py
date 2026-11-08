"""Label PDFs come from document-svc; if it is down the units are still allocated (fileId null)."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from inventory_svc.documents import DocumentLabels


def _transport(fail: bool = False) -> tuple[httpx.MockTransport, list[dict[str, object]]]:
    seen: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/internal/service-token"):
            assert json.loads(request.content)["service"] == "inventory"
            return httpx.Response(200, json={"token": "t", "expiresIn": 300})
        assert request.url.path == "/api/documents/v1/internal/labels"
        assert request.headers["authorization"] == "Bearer t"
        if fail:
            return httpx.Response(503, json={"code": "DEPENDENCY_UNAVAILABLE"})
        seen.append(json.loads(request.content))
        return httpx.Response(201, json={"id": "FIL0123456789abcdef", "kind": "labels"})

    return httpx.MockTransport(handler), seen


@pytest.mark.req("I2")
def test_render_returns_the_file_id() -> None:
    transport, seen = _transport()
    labels = DocumentLabels("http://document", "http://identity", "s", transport=transport)
    assert asyncio.run(labels.render("MET1", "Rain gauge", ["MET1_00000001"])) == "FIL0123456789abcdef"
    assert seen == [{"productId": "MET1", "productName": "Rain gauge", "barcodes": ["MET1_00000001"]}]


def test_document_svc_down_gives_no_file() -> None:
    transport, _ = _transport(fail=True)
    labels = DocumentLabels("http://document", "http://identity", "s", transport=transport)
    assert asyncio.run(labels.render("MET1", None, ["MET1_00000001"])) is None
