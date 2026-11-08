"""HTTP layer for order-svc: docs/api/orders.openapi.yaml is the contract.

Customers (role user, not @cimh.edu.bb) own carts and submit requests; customer actions are the requester's or
an admin's; staff actions need staff/admin. State changes need `If-Match: <version>` (428 without it).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from cimh_common.auth import Principal
from cimh_common.authz import require_requester, require_roles, require_service, require_staff
from cimh_common.errors import ProblemError, forbidden
from cimh_common.idempotency import IdempotencyStore, fingerprint

from .service import OrderService

MoneyStr = Annotated[str, Field(pattern=r"^-?\d{1,12}\.\d{2}$")]
Currency = Literal["BBD", "USD"]
Status = Literal[
    "SUBMITTED",
    "QUOTING",
    "QUOTED",
    "AWAITING_AGREEMENT",
    "ACCEPTED",
    "DECLINED",
    "PURCHASING",
    "APPROVED",
    "REJECTED",
    "PICKING",
    "SHIPPED",
    "DELIVERED",
    "CANCELLED",
]
IfMatch = Annotated[str | None, Header(alias="If-Match")]
Id = Annotated[str, Field(min_length=1, max_length=64)]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Address(Strict):
    line1: str = Field(min_length=1, max_length=200)
    line2: str | None = Field(default=None, max_length=200)
    city: str = Field(min_length=1, max_length=100)
    parish: str | None = Field(default=None, max_length=100)
    country: str = Field(pattern=r"^[A-Z]{2}$")
    zip: str | None = Field(default=None, max_length=20)
    organisation: str | None = Field(default=None, max_length=200)
    attention: str | None = Field(default=None, max_length=200)
    firstname: str = Field(min_length=1, max_length=100)
    lastname: str = Field(min_length=1, max_length=100)
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=254)
    tel: str | None = Field(default=None, max_length=40)


class QtyIn(Strict):
    qty: int = Field(ge=1, le=9999)


class SubmitIn(Strict):
    currency: Currency | None = None
    shipTo: Address
    billTo: Address | None = None
    notes: str | None = Field(default=None, max_length=2000)


class ReasonIn(Strict):
    reason: str = Field(min_length=3, max_length=500)


class Choice(Strict):
    lineId: Id
    choice: Literal["CIMH", "SUPPLIER"]


class AgreementIn(Strict):
    quoteVersion: int
    choices: list[Choice] = Field(max_length=200)


class AcceptIn(Strict):
    quoteVersion: int
    signedAgreementFileId: Id


class PriceLine(Strict):
    lineId: Id
    unitPrice: MoneyStr


class SupplierQuoteIn(Strict):
    supplier: str = Field(min_length=1, max_length=200)
    lines: list[PriceLine] = Field(max_length=200)
    fileIds: list[Id] = Field(max_length=20)


class CimhIn(Strict):
    lineIds: list[Id] = Field(default_factory=list, max_length=200)
    exchangeRate: str | None = Field(default=None, pattern=r"^\d+(\.\d{1,6})?$")


class DraftIn(Strict):
    supplierQuotes: list[SupplierQuoteIn] = Field(max_length=20)
    cimh: CimhIn | None = None


class PurchaseOrder(Strict):
    supplier: str = Field(min_length=1, max_length=200)
    poNumber: str = Field(min_length=1, max_length=100)
    lineIds: list[Id] = Field(min_length=1, max_length=200)


class PurchaseOrdersIn(Strict):
    agreementVerified: bool
    purchaseOrders: list[PurchaseOrder] = Field(max_length=50)


class PickIn(Strict):
    lineId: Id
    unit: Annotated[str, Field(min_length=1, max_length=128)]


class ShipIn(BaseModel):
    model_config = ConfigDict(extra="forbid")  # `date` arrives as a string: not strict

    carrier: Literal["FEDEX", "DHL", "HAND"]
    tracking: str | None = Field(default=None, max_length=100)
    note: str | None = Field(default=None, max_length=300)
    cost: MoneyStr | None = None
    date: date
    notifyCustomer: bool = True


class DeliverIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invoiceNumber: str | None = Field(default=None, min_length=1, max_length=50)
    deliveredAt: datetime | None = None


class FileIn(Strict):
    id: Id
    kind: Literal[
        "supplier_quote",
        "cimh_quote",
        "agreement",
        "signed_agreement",
        "invoice",
        "commercial_invoice",
        "probono_invoice",
        "upload",
    ]
    name: str = Field(min_length=1, max_length=255)
    mime: str = Field(min_length=1, max_length=100)
    size: int = Field(ge=0)
    uploadedAt: str | None = None
    url: str | None = None
    sha256: str | None = None


router = APIRouter()
require_customer_or_admin = require_roles("user", "admin")
require_any = require_roles("user", "staff", "admin")


def svc(request: Request) -> OrderService:
    s: OrderService = request.app.state.orders
    return s


def cid(request: Request) -> str:
    return str(getattr(request.state, "trace_id", "") or "")


def if_match(value: str | None) -> int:
    if not value:
        raise ProblemError(428, "PRECONDITION_REQUIRED", "If-Match header with the current version is required")
    try:
        return int(value.strip().removeprefix("W/").strip('"'))
    except ValueError as exc:
        raise ProblemError(400, None, "If-Match must be a version number") from exc


def with_etag(body: dict[str, Any], status: int = 200) -> JSONResponse:
    return JSONResponse(body, status_code=status, headers={"ETag": f'"{body["version"]}"'})


def client_ip(request: Request) -> str | None:
    """nginx sets X-Real-IP at the edge (TAD §8); behind it the socket peer is nginx itself."""
    return request.headers.get("x-real-ip") or (request.client.host if request.client else None)


def require_document_svc(me: Principal = Depends(require_service)) -> Principal:
    if me.sub != "svc:document":
        raise forbidden("Only document-svc may call this endpoint")
    return me


# ---------------------------------------------------------------- cart


@router.get("/cart", tags=["cart"])
async def get_cart(request: Request, me: Principal = Depends(require_requester)) -> dict[str, Any]:
    return await svc(request).cart(me)


@router.delete("/cart", status_code=204, tags=["cart"])
async def empty_cart(request: Request, me: Principal = Depends(require_requester)) -> Response:
    await svc(request).empty_cart(me)
    return Response(status_code=204)


@router.put("/cart/lines/{productId}", tags=["cart"])
async def set_line(
    productId: str, body: QtyIn, request: Request, me: Principal = Depends(require_requester)
) -> dict[str, Any]:
    return await svc(request).set_line(me, productId, body.qty)


@router.delete("/cart/lines/{productId}", tags=["cart"])
async def remove_line(productId: str, request: Request, me: Principal = Depends(require_requester)) -> dict[str, Any]:
    return await svc(request).remove_line(me, productId)


# ---------------------------------------------------------------- requests


@router.post("/requests", status_code=201, tags=["requests"])
async def submit(
    body: SubmitIn,
    request: Request,
    key: Annotated[str | None, Header(alias="Idempotency-Key", max_length=64)] = None,
    me: Principal = Depends(require_requester),
) -> Any:
    data = body.model_dump(exclude_none=True)

    async def call() -> dict[str, Any]:
        return {"requests": await svc(request).submit(me, data, cid(request))}

    if not key:
        return JSONResponse(await call(), status_code=201)
    store: IdempotencyStore = request.app.state.idempotency
    out = await store.run(scope=f"{me.sub}:submit", key=key, fingerprint=fingerprint(data), call=call)
    return JSONResponse(out, status_code=201)


@router.get("/requests", tags=["requests"])
async def list_requests(
    request: Request,
    scope: Literal["mine", "organisation", "all"] = "mine",
    status: Annotated[str | None, Query()] = None,
    type: Literal["PAID", "PROBONO"] | None = None,
    year: Annotated[int | None, Query(ge=2000, le=2100)] = None,
    customer: Annotated[str | None, Query(max_length=64)] = None,
    organisationId: Annotated[str | None, Query(max_length=64)] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    sort: Literal["newest", "oldest", "waiting"] = "newest",
    cursor: Annotated[str | None, Query(max_length=500)] = None,
    limit: Annotated[int | None, Query(ge=1, le=100)] = None,
    me: Principal = Depends(require_any),
) -> dict[str, Any]:
    statuses = status.split(",") if status is not None else []
    allowed = set(Status.__args__)  # type: ignore[attr-defined]
    bad = [s for s in statuses if s not in allowed]
    if bad:
        raise ProblemError(422, "VALIDATION_FAILED", errors=[{"field": "status", "message": f"unknown {bad[0]}"}])
    filters = {"scope": scope, "status": statuses, "type": type, "year": year, "customer": customer}
    filters |= {"organisationId": organisationId, "q": q, "sort": sort}
    items, nxt = await svc(request).list_requests(me, filters, cursor, limit)
    return {"items": items, "nextCursor": nxt}


@router.get("/requests/{requestId}", tags=["requests"])
async def get_request(requestId: str, request: Request, me: Principal = Depends(require_any)) -> JSONResponse:
    return with_etag(await svc(request).get(me, requestId))


# ---------------------------------------------------------------- customer actions


@router.post("/requests/{requestId}/agreement", tags=["customer-actions"])
async def agreement(
    requestId: str,
    body: AgreementIn,
    request: Request,
    v: IfMatch = None,
    me: Principal = Depends(require_customer_or_admin),
) -> JSONResponse:
    out = await svc(request).agreement(me, requestId, if_match(v), body.model_dump(), cid(request))
    return with_etag(out)


@router.post("/requests/{requestId}/accept", tags=["customer-actions"])
async def accept(
    requestId: str,
    body: AcceptIn,
    request: Request,
    v: IfMatch = None,
    me: Principal = Depends(require_customer_or_admin),
) -> JSONResponse:
    out = await svc(request).accept(me, requestId, if_match(v), body.model_dump(), client_ip(request), cid(request))
    return with_etag(out)


@router.post("/requests/{requestId}/decline", tags=["customer-actions"])
async def decline(
    requestId: str,
    body: ReasonIn,
    request: Request,
    v: IfMatch = None,
    me: Principal = Depends(require_customer_or_admin),
) -> JSONResponse:
    return with_etag(await svc(request).decline(me, requestId, if_match(v), body.reason, cid(request)))


@router.post("/requests/{requestId}/cancel", tags=["customer-actions"])
async def cancel(
    requestId: str, body: ReasonIn, request: Request, v: IfMatch = None, me: Principal = Depends(require_any)
) -> JSONResponse:
    return with_etag(await svc(request).cancel(me, requestId, if_match(v), body.reason, cid(request)))


# ---------------------------------------------------------------- staff actions


@router.post("/requests/{requestId}/start-quoting", tags=["staff-actions"])
async def start_quoting(
    requestId: str, request: Request, v: IfMatch = None, me: Principal = Depends(require_staff)
) -> JSONResponse:
    return with_etag(await svc(request).start_quoting(me, requestId, if_match(v), cid(request)))


@router.put("/requests/{requestId}/quote-draft", tags=["staff-actions"])
async def quote_draft(
    requestId: str, body: DraftIn, request: Request, v: IfMatch = None, me: Principal = Depends(require_staff)
) -> JSONResponse:
    return with_etag(await svc(request).save_draft(me, requestId, if_match(v), body.model_dump()))


@router.post("/requests/{requestId}/send-quote", tags=["staff-actions"])
async def send_quote(
    requestId: str, request: Request, v: IfMatch = None, me: Principal = Depends(require_staff)
) -> JSONResponse:
    return with_etag(await svc(request).send_quote(me, requestId, if_match(v), cid(request)))


@router.post("/requests/{requestId}/reject-agreement", tags=["staff-actions"])
async def reject_agreement(
    requestId: str, body: ReasonIn, request: Request, v: IfMatch = None, me: Principal = Depends(require_staff)
) -> JSONResponse:
    return with_etag(await svc(request).reject_agreement(me, requestId, if_match(v), body.reason, cid(request)))


@router.post("/requests/{requestId}/purchase-orders", tags=["staff-actions"])
async def purchase_orders(
    requestId: str, body: PurchaseOrdersIn, request: Request, v: IfMatch = None, me: Principal = Depends(require_staff)
) -> JSONResponse:
    return with_etag(await svc(request).purchase_orders(me, requestId, if_match(v), body.model_dump(), cid(request)))


@router.post("/requests/{requestId}/approve", tags=["staff-actions"])
async def approve(
    requestId: str, request: Request, v: IfMatch = None, me: Principal = Depends(require_staff)
) -> JSONResponse:
    return with_etag(await svc(request).approve(me, requestId, if_match(v), cid(request)))


@router.post("/requests/{requestId}/reject", tags=["staff-actions"])
async def reject(
    requestId: str, body: ReasonIn, request: Request, v: IfMatch = None, me: Principal = Depends(require_staff)
) -> JSONResponse:
    return with_etag(await svc(request).reject(me, requestId, if_match(v), body.reason, cid(request)))


@router.post("/requests/{requestId}/picks", tags=["staff-actions"])
async def pick(
    requestId: str,
    body: PickIn,
    request: Request,
    key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=64)],
    me: Principal = Depends(require_staff),
) -> JSONResponse:
    store: IdempotencyStore = request.app.state.idempotency

    async def call() -> dict[str, Any]:
        return await svc(request).pick(me, requestId, body.lineId, body.unit, key, cid(request))

    out = await store.run(
        scope=f"{me.sub}:pick:{requestId}", key=key, fingerprint=fingerprint(body.model_dump()), call=call
    )
    return with_etag(out)


@router.post("/requests/{requestId}/ship", tags=["staff-actions"])
async def ship(
    requestId: str, body: ShipIn, request: Request, v: IfMatch = None, me: Principal = Depends(require_staff)
) -> JSONResponse:
    data = body.model_dump()
    data["date"] = body.date.isoformat()
    return with_etag(await svc(request).ship(me, requestId, if_match(v), data, cid(request)))


@router.post("/requests/{requestId}/deliver", tags=["staff-actions"])
async def deliver(
    requestId: str,
    request: Request,
    body: DeliverIn | None = None,
    v: IfMatch = None,
    me: Principal = Depends(require_staff),
) -> JSONResponse:
    data = (body or DeliverIn()).model_dump(exclude_none=True)
    return with_etag(await svc(request).deliver(me, requestId, if_match(v), data, cid(request)))


# ---------------------------------------------------------------- internal (document-svc; not routed by nginx)


@router.get("/internal/requests/{requestId}/access", tags=["internal"])
async def access(
    requestId: str,
    request: Request,
    user: Annotated[str, Query(min_length=1, max_length=64)],
    me: Principal = Depends(require_document_svc),
) -> dict[str, Any]:
    return await svc(request).access(requestId, user)


@router.get("/internal/requests/{requestId}", tags=["internal"])
async def internal_get(
    requestId: str, request: Request, me: Principal = Depends(require_document_svc)
) -> dict[str, Any]:
    return await svc(request).internal_get(requestId)


@router.post("/internal/requests/{requestId}/files", status_code=204, tags=["internal"])
async def attach(
    requestId: str, body: FileIn, request: Request, me: Principal = Depends(require_document_svc)
) -> Response:
    await svc(request).attach_file(requestId, body.model_dump())
    return Response(status_code=204)
