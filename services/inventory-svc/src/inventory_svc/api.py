"""HTTP layer for inventory-svc: docs/api/inventory.openapi.yaml is the contract.

All public endpoints are staff/admin. Scans need an `Idempotency-Key` (a replay returns the first answer).
Internal endpoints accept order-svc's service token only.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator

from cimh_common.auth import Principal
from cimh_common.authz import require_service, require_staff
from cimh_common.errors import ProblemError, forbidden
from cimh_common.idempotency import IdempotencyStore, fingerprint

from .service import InventoryService

Limit = Annotated[int | None, Query(ge=1, le=100)]
Code = Annotated[str, Field(min_length=1, max_length=128)]
ScanKey = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=64)]
Operation = Literal["stow", "pick", "relocate", "assign", "unassign", "reserve", "release", "adjust"]
# RFC 3339 date-time with an offset (pydantic alone would also take Unix numbers like "0.5").
DateTime = Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$")]


def parse_dt(value: str | None, name: str) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProblemError(422, "VALIDATION_FAILED", errors=[{"field": name, "message": "not a date-time"}]) from exc


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class SiteIn(Strict):
    name: str = Field(min_length=1, max_length=200)
    country: str = Field(pattern=r"^[A-Z]{2}$")
    address: str | None = Field(default=None, max_length=500)
    description: str | None = Field(default=None, max_length=500)


class LocationIn(Strict):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=500)


class ShelvesIn(Strict):
    count: int = Field(ge=1, le=200)


class LabelsIn(Strict):
    productId: Code
    quantity: int = Field(ge=1, le=500)
    format: Literal["pdf", "csv"] = "pdf"
    serials: list[Annotated[str, Field(max_length=100)]] | None = Field(default=None, max_length=500)


class StowIn(Strict):
    unit: Code
    shelf: Code


class PickIn(Strict):
    unit: Code
    reason: str | None = Field(default=None, min_length=1, max_length=300)
    orderId: str | None = Field(default=None, min_length=1, max_length=64)

    @model_validator(mode="after")
    def one_of(self) -> PickIn:
        if (self.reason is None) == (self.orderId is None):
            raise ValueError("give either a reason or an orderId")
        return self


class RelocateIn(Strict):
    unit: Code
    toShelf: Code


class AssignIn(Strict):
    unit: Code
    accountId: str = Field(min_length=1, max_length=64)


class UnitIn(Strict):
    unit: Code


class Line(Strict):
    lineId: str = Field(min_length=1, max_length=64)
    productId: Code
    qty: int = Field(ge=1, le=10_000)


class LinesIn(Strict):
    lines: list[Line] = Field(min_length=1, max_length=200)


class ReserveIn(LinesIn):
    orderId: str = Field(min_length=1, max_length=64)


router = APIRouter()


def svc(request: Request) -> InventoryService:
    s: InventoryService = request.app.state.inventory
    return s


def cid(request: Request) -> str:
    return str(getattr(request.state, "trace_id", "") or "")


async def scan(
    request: Request, me: Principal, op: str, key: str, body: BaseModel, call: Callable[[], Awaitable[Any]]
) -> Any:
    store: IdempotencyStore = request.app.state.idempotency
    return await store.run(scope=f"{me.sub}:{op}", key=key, fingerprint=fingerprint(body.model_dump()), call=call)


def require_order_svc(me: Principal = Depends(require_service)) -> Principal:
    if me.sub != "svc:order":
        raise forbidden("Only order-svc may call this endpoint")
    return me


# ---------------------------------------------------------------- places (I1)


@router.get("/sites", tags=["places"])
async def sites(request: Request, me: Principal = Depends(require_staff)) -> dict[str, Any]:
    return {"items": await svc(request).sites()}


@router.post("/sites", status_code=201, tags=["places"])
async def create_site(body: SiteIn, request: Request, me: Principal = Depends(require_staff)) -> dict[str, Any]:
    return await svc(request).create_site(me, body.model_dump(exclude_none=True))


@router.get("/sites/{site}/locations", tags=["places"])
async def locations(
    site: str, request: Request, withShelves: bool = False, me: Principal = Depends(require_staff)
) -> dict[str, Any]:
    return {"items": await svc(request).locations(site, withShelves)}


@router.post("/sites/{site}/locations", status_code=201, tags=["places"])
async def create_location(
    site: str, body: LocationIn, request: Request, me: Principal = Depends(require_staff)
) -> dict[str, Any]:
    return await svc(request).create_location(me, site, body.model_dump(exclude_none=True))


@router.post("/locations/{location}/shelves", status_code=201, tags=["places"])
async def add_shelves(
    location: str, body: ShelvesIn, request: Request, me: Principal = Depends(require_staff)
) -> dict[str, Any]:
    return {"items": await svc(request).add_shelves(me, location, body.count)}


@router.get("/shelves/{barcode}", tags=["places"])
async def shelf(barcode: str, request: Request, me: Principal = Depends(require_staff)) -> dict[str, Any]:
    return await svc(request).shelf(barcode)


# ---------------------------------------------------------------- units (I2, I7)


@router.get("/shelves/{barcode}/units", tags=["units"])
async def shelf_units(
    barcode: str,
    request: Request,
    cursor: str | None = None,
    limit: Limit = None,
    me: Principal = Depends(require_staff),
) -> dict[str, Any]:
    items, nxt = await svc(request).shelf_units(barcode, cursor, limit)
    return {"items": items, "nextCursor": nxt}


@router.get("/units/{barcode}", tags=["units"])
async def unit(barcode: str, request: Request, me: Principal = Depends(require_staff)) -> dict[str, Any]:
    return await svc(request).unit(barcode)


@router.post("/labels", status_code=201, tags=["units"])
async def labels(body: LabelsIn, request: Request, me: Principal = Depends(require_staff)) -> dict[str, Any]:
    return await svc(request).labels(me, body.productId, body.quantity, body.serials)


# ---------------------------------------------------------------- scans (I3-I6)


@router.post("/stow", tags=["scans"])
async def stow(body: StowIn, request: Request, key: ScanKey, me: Principal = Depends(require_staff)) -> Any:
    return await scan(
        request, me, "stow", key, body, lambda: svc(request).stow(me, body.unit, body.shelf, cid(request))
    )


@router.post("/pick", tags=["scans"])
async def pick(body: PickIn, request: Request, key: ScanKey, me: Principal = Depends(require_staff)) -> Any:
    return await scan(
        request,
        me,
        "pick",
        key,
        body,
        lambda: svc(request).pick(me, body.unit, body.reason, body.orderId, cid(request)),
    )


@router.post("/relocate", tags=["scans"])
async def relocate(body: RelocateIn, request: Request, key: ScanKey, me: Principal = Depends(require_staff)) -> Any:
    return await scan(
        request, me, "relocate", key, body, lambda: svc(request).relocate(me, body.unit, body.toShelf, cid(request))
    )


@router.post("/assign", tags=["scans"])
async def assign(body: AssignIn, request: Request, key: ScanKey, me: Principal = Depends(require_staff)) -> Any:
    return await scan(
        request, me, "assign", key, body, lambda: svc(request).assign(me, body.unit, body.accountId, cid(request))
    )


@router.post("/unassign", tags=["scans"])
async def unassign(body: UnitIn, request: Request, key: ScanKey, me: Principal = Depends(require_staff)) -> Any:
    return await scan(request, me, "unassign", key, body, lambda: svc(request).unassign(me, body.unit, cid(request)))


# ---------------------------------------------------------------- stock (I4, I8, I10)


@router.get("/products/{productId}/stock", tags=["stock"])
async def product_stock(productId: str, request: Request, me: Principal = Depends(require_staff)) -> dict[str, Any]:
    return await svc(request).product_stock(productId)


@router.get("/stock/low", tags=["stock"])
async def low_stock(
    request: Request, cursor: str | None = None, limit: Limit = None, me: Principal = Depends(require_staff)
) -> dict[str, Any]:
    items, nxt = await svc(request).low_stock(cursor, limit)
    return {"items": items, "nextCursor": nxt}


@router.get("/assignments", tags=["stock"])
async def assignments(
    request: Request,
    accountId: str | None = None,
    cursor: str | None = None,
    limit: Limit = None,
    me: Principal = Depends(require_staff),
) -> dict[str, Any]:
    items, nxt = await svc(request).assignments(accountId, cursor, limit)
    return {"items": items, "nextCursor": nxt}


@router.get("/history", tags=["stock"])
async def history(
    request: Request,
    unit: str | None = None,
    user: str | None = None,
    operation: Operation | None = None,
    from_: Annotated[DateTime, Query(alias="from")] = None,
    to: DateTime = None,
    cursor: str | None = None,
    limit: Limit = None,
    me: Principal = Depends(require_staff),
) -> dict[str, Any]:
    filters: dict[str, Any] = {"unit": unit, "user": user, "operation": operation}
    filters |= {"from": parse_dt(from_, "from"), "to": parse_dt(to, "to")}
    items, nxt = await svc(request).history(filters, cursor, limit)
    return {"items": items, "nextCursor": nxt}


# ---------------------------------------------------------------- internal (order-svc; not routed by nginx)


@router.post("/internal/availability", tags=["internal"])
async def availability(body: LinesIn, request: Request, me: Principal = Depends(require_order_svc)) -> dict[str, Any]:
    return {"lines": await svc(request).availability([line.model_dump() for line in body.lines])}


@router.post("/internal/reservations", tags=["internal"])
async def reserve(body: ReserveIn, request: Request, me: Principal = Depends(require_order_svc)) -> dict[str, Any]:
    lines = [line.model_dump() for line in body.lines]
    return {"lines": await svc(request).reserve(me, body.orderId, lines, cid(request))}


@router.delete("/internal/reservations/{orderId}", status_code=204, tags=["internal"])
async def release(orderId: str, request: Request, me: Principal = Depends(require_order_svc)) -> Response:
    await svc(request).release(me, orderId, cid(request))
    return Response(status_code=204)
