"""HTTP layer for catalog-svc: docs/api/catalog.openapi.yaml is the contract."""

from __future__ import annotations

import re
import secrets
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, File, Form, Header, Query, Request, Response, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from cimh_common.auth import Principal
from cimh_common.authz import optional_principal, require_admin, require_services, require_staff
from cimh_common.errors import ProblemError

from .service import CatalogService

ProductType = Literal["MET", "RAD", "EQUIP", "SUPP", "MISC", "PRO"]
Money = Annotated[str, Field(pattern=r"^-?\d{1,12}\.\d{2}$")]
Limit = Annotated[int | None, Query(ge=1, le=100)]
IfMatch = Annotated[str | None, Header(alias="If-Match")]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ProductPatch(Strict):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    details: str | None = Field(default=None, max_length=5000)
    make: str | None = Field(default=None, max_length=100)
    modelname: str | None = Field(default=None, max_length=100)
    modelnumber: str | None = Field(default=None, max_length=100)
    type: ProductType | None = None
    department: str | None = Field(default=None, min_length=1, max_length=100)
    project: str | None = Field(default=None, max_length=50)
    sellable: bool | None = None
    probono: bool | None = None
    probonoMaxPerRequest: int | None = Field(default=None, ge=1)
    cost: Money | None = None
    threshold: int | None = Field(default=None, ge=0)
    unitquantity: int | None = Field(default=None, ge=1)
    weight: float | None = Field(default=None, ge=0)
    dimension: str | None = Field(default=None, max_length=100)
    sn: str | None = Field(default=None, max_length=100)
    sn1: str | None = Field(default=None, max_length=100)
    keywords: list[Annotated[str, Field(max_length=50)]] | None = Field(default=None, max_length=50)


class ProductInput(ProductPatch):
    id: str | None = Field(default=None, min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")
    name: str = Field(min_length=1, max_length=200)
    type: ProductType
    department: str = Field(min_length=1, max_length=100)
    sellable: bool
    probono: bool
    threshold: int = Field(ge=0)


class ValuesIn(Strict):
    values: list[Annotated[str, Field(max_length=100)]] = Field(max_length=200)


class ProjectIn(Strict):
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=200)
    active: bool = True


class ProjectPatch(Strict):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    active: bool | None = None


class Fee(Strict):
    name: str = Field(min_length=1, max_length=50)
    fee: Money


class FeesIn(Strict):
    types: list[Fee] = Field(max_length=50)


class Member(BaseModel):
    model_config = ConfigDict(
        extra="ignore", strict=True
    )  # read-only echo fields (email, names) are allowed and ignored
    accountId: str = Field(min_length=1, max_length=64)


class EmailListsIn(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    registration: list[Member] = Field(max_length=50)
    order: list[Member] = Field(max_length=50)
    invoice: list[Member] = Field(max_length=50)
    cancellation: list[Member] = Field(max_length=50)
    lowStock: list[Member] = Field(max_length=50)


class SettingsIn(Strict):
    quoteValidityDays: int = Field(ge=1, le=365)
    quoteReminderDays: int = Field(ge=0, le=60)
    approvalReminderHours: int = Field(ge=1, le=720)
    purgeAfterDays: int = Field(ge=1, le=3650)
    cartInactivityDays: int = Field(default=180, ge=1, le=3650)


class IdsIn(Strict):
    ids: list[Annotated[str, Field(max_length=64)]] = Field(max_length=200)


class PlaceIn(Strict):
    kind: Literal["site", "location", "shelf"]
    barcode: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    site: str | None = Field(default=None, max_length=64)
    location: str | None = Field(default=None, max_length=64)
    number: int | None = None
    country: str | None = Field(default=None, max_length=2)
    address: str | None = Field(default=None, max_length=500)
    description: str | None = Field(default=None, max_length=500)
    active: bool


class PrimaryIn(Strict):
    primary: Literal[True]


# ---------------------------------------------------------------- helpers


def svc(request: Request) -> CatalogService:
    s: CatalogService = request.app.state.catalog
    return s


def cid(request: Request) -> str:
    return str(getattr(request.state, "trace_id", "") or "none")


def if_match(value: str | None) -> int:
    if not value:
        raise ProblemError(428, "PRECONDITION_REQUIRED", "If-Match header with the current version is required")
    try:
        return int(value.strip().removeprefix("W/").strip('"'))
    except ValueError as exc:
        raise ProblemError(400, None, "If-Match must be a version number") from exc


def with_etag(body: dict[str, Any], status: int = 200) -> JSONResponse:
    headers = {"ETag": f'"{body["version"]}"'} if "version" in body else {}
    return JSONResponse(body, status_code=status, headers=headers)


IMAGE_MAGIC: tuple[tuple[bytes, int, str], ...] = (
    (b"\xff\xd8\xff", 0, ".jpg"),
    (b"\x89PNG\r\n\x1a\n", 0, ".png"),
    (b"WEBP", 8, ".webp"),
)


def image_ext(head: bytes) -> str | None:
    """Trust the bytes, never the file name or the Content-Type header."""
    for magic, offset, ext in IMAGE_MAGIC:
        if head[offset : offset + len(magic)] == magic and (ext != ".webp" or head[:4] == b"RIFF"):
            return ext
    return None


# Internal endpoints: who may call them (least privilege, pen test 2026-11).
FROM_ORDER_INVENTORY = require_services("order", "inventory")
FROM_NOTIFICATION = require_services("notification")
FROM_ORDER = require_services("order")
FROM_INVENTORY = require_services("inventory")

router = APIRouter()

# ---------------------------------------------------------------- products


@router.get("/products", tags=["products"])
async def list_products(
    request: Request,
    type: ProductType | None = None,
    department: str | None = None,
    project: str | None = None,
    probono: bool | None = None,
    inStock: bool | None = None,
    sellable: bool | None = None,
    includeInactive: bool = False,
    cursor: str | None = None,
    limit: Limit = None,
    me: Principal | None = Depends(optional_principal),
) -> dict[str, Any]:
    filters = {
        "type": type,
        "department": department,
        "project": project,
        "probono": probono,
        "inStock": inStock,
        "sellable": sellable,
        "includeInactive": includeInactive,
    }
    items, nxt = await svc(request).list_products(me, filters, cursor, limit)
    return {"items": items, "nextCursor": nxt}


@router.post("/products", status_code=201, tags=["products"])
async def create_product(body: ProductInput, request: Request, me: Principal = Depends(require_staff)) -> JSONResponse:
    created = await svc(request).create_product(me, body.model_dump(exclude_unset=True), cid(request))
    return with_etag(created, 201)


@router.get("/products/search", tags=["products"])
async def search(
    request: Request,
    q: Annotated[str, Query(min_length=2, max_length=100)],
    type: ProductType | None = None,
    department: str | None = None,
    probono: bool | None = None,
    cursor: str | None = None,
    limit: Limit = None,
    me: Principal | None = Depends(optional_principal),
) -> dict[str, Any]:
    filters = {"type": type, "department": department, "probono": probono}
    items, nxt = await svc(request).search(me, q, filters, cursor, limit)
    return {"items": items, "nextCursor": nxt}


@router.get("/products/{productId}", tags=["products"])
async def get_product(
    productId: str, request: Request, me: Principal | None = Depends(optional_principal)
) -> JSONResponse:
    return with_etag(await svc(request).get_product(me, productId))


@router.patch("/products/{productId}", tags=["products"])
async def patch_product(
    productId: str,
    body: ProductPatch,
    request: Request,
    version: IfMatch = None,
    me: Principal = Depends(require_staff),
) -> JSONResponse:
    fields = body.model_dump(exclude_unset=True)
    for required in ("name", "type", "department", "sellable", "probono", "threshold"):
        if required in fields and fields[required] is None:
            raise ProblemError(422, "VALIDATION_FAILED", errors=[{"field": required, "message": "cannot be empty"}])
    if not fields:
        raise ProblemError(422, "VALIDATION_FAILED", "Nothing to update")
    return with_etag(await svc(request).update_product(me, productId, if_match(version), fields, cid(request)))


@router.delete("/products/{productId}", status_code=204, tags=["products"])
async def delete_product(
    productId: str, request: Request, version: IfMatch = None, me: Principal = Depends(require_staff)
) -> Response:
    await svc(request).deactivate_product(me, productId, if_match(version), cid(request))
    return Response(status_code=204)


# ---------------------------------------------------------------- images


@router.post("/products/{productId}/images", status_code=202, tags=["images"])
async def upload_images(
    productId: str,
    request: Request,
    files: Annotated[list[UploadFile], File()],
    removeBackground: Annotated[bool, Form()] = False,
    me: Principal = Depends(require_staff),
) -> dict[str, Any]:
    s = request.app.state.settings
    if not files or len(files) > s.max_images_per_upload:
        raise ProblemError(422, "VALIDATION_FAILED", f"1 to {s.max_images_per_upload} images per upload")
    if await svc(request).store.product.find_one({"id": productId}, {"_id": 1}) is None:
        raise ProblemError(404, "NOT_FOUND", "Product not found")
    incoming = Path(s.media_root) / "incoming"
    incoming.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    try:
        for f in files:
            data = await f.read(s.max_image_bytes + 1)
            if len(data) > s.max_image_bytes:
                raise ProblemError(413, "FILE_TOO_LARGE", f"{f.filename}: larger than {s.max_image_bytes // 2**20} MB")
            ext = image_ext(data[:16])
            if ext is None:
                raise ProblemError(
                    422, "UNSUPPORTED_MEDIA_TYPE", f"{f.filename}: only JPEG, PNG and WebP images are accepted"
                )
            path = incoming / f"{secrets.token_hex(16)}{ext}"
            path.write_bytes(data)
            written.append(path)
        sources = [f"incoming/{p.name}" for p in written]
        jobs = await svc(request).queue_images(me, productId, sources, removeBackground, cid(request))
    except Exception:
        for p in written:
            p.unlink(missing_ok=True)
        raise
    return {"jobIds": jobs}


@router.patch("/products/{productId}/images/{fileId}", tags=["images"])
async def primary_image(
    productId: str, fileId: str, body: PrimaryIn, request: Request, me: Principal = Depends(require_staff)
) -> JSONResponse:
    return with_etag(await svc(request).set_primary_image(me, productId, fileId, cid(request)))


@router.delete("/products/{productId}/images/{fileId}", status_code=204, tags=["images"])
async def delete_image(
    productId: str, fileId: str, request: Request, me: Principal = Depends(require_staff)
) -> Response:
    await svc(request).remove_image(me, productId, fileId, cid(request))
    # media-worker writes public/products/<productId>/<fileId>[@800|@320].webp (BSD §2). Both ids exist on a
    # product we just changed, and neither may contain a path.
    safe = re.compile(r"[A-Za-z0-9._-]{1,64}")
    if safe.fullmatch(fileId) and safe.fullmatch(productId) and ".." not in productId:
        folder = Path(request.app.state.settings.media_root) / "public" / "products" / productId
        for f in folder.glob(f"{fileId}*.webp"):
            f.unlink(missing_ok=True)
    return Response(status_code=204)


# ---------------------------------------------------------------- reference


@router.get("/reference", tags=["reference"])
async def reference(
    request: Request, includeInactive: bool = False, me: Principal | None = Depends(optional_principal)
) -> dict[str, Any]:
    return await svc(request).reference(include_inactive=bool(includeInactive and me and me.is_staff))


@router.put("/reference/departments", status_code=204, tags=["reference"])
async def put_departments(body: ValuesIn, request: Request, me: Principal = Depends(require_admin)) -> Response:
    await svc(request).put_departments(me, body.values, cid(request))
    return Response(status_code=204)


@router.post("/reference/projects", status_code=201, tags=["reference"])
async def create_project(body: ProjectIn, request: Request, me: Principal = Depends(require_admin)) -> JSONResponse:
    return JSONResponse(await svc(request).create_project(me, body.model_dump(), cid(request)), status_code=201)


@router.patch("/reference/projects/{code}", tags=["reference"])
async def patch_project(
    code: str, body: ProjectPatch, request: Request, me: Principal = Depends(require_admin)
) -> dict[str, Any]:
    return await svc(request).update_project(me, code, body.model_dump(exclude_unset=True), cid(request))


# ---------------------------------------------------------------- settings


@router.get("/settings/fees", tags=["settings"])
async def get_fees(request: Request, me: Principal = Depends(require_staff)) -> dict[str, Any]:
    return await svc(request).fees()


@router.put("/settings/fees", tags=["settings"])
async def put_fees(body: FeesIn, request: Request, me: Principal = Depends(require_admin)) -> dict[str, Any]:
    return await svc(request).put_fees(me, body.model_dump(), cid(request))


@router.get("/settings/email-lists", tags=["settings"])
async def get_email_lists(request: Request, me: Principal = Depends(require_admin)) -> dict[str, Any]:
    return await svc(request).email_lists()


@router.put("/settings/email-lists", tags=["settings"])
async def put_email_lists(
    body: EmailListsIn, request: Request, me: Principal = Depends(require_admin)
) -> dict[str, Any]:
    return await svc(request).put_email_lists(me, body.model_dump(), cid(request))


@router.get("/settings/general", tags=["settings"])
async def get_general(request: Request, me: Principal = Depends(require_staff)) -> dict[str, Any]:
    return await svc(request).general()


@router.put("/settings/general", tags=["settings"])
async def put_general(body: SettingsIn, request: Request, me: Principal = Depends(require_admin)) -> dict[str, Any]:
    return await svc(request).put_general(me, body.model_dump(), cid(request))


# ---------------------------------------------------------------- internal (service tokens; not routed by nginx)


@router.post("/internal/products/summaries", tags=["internal"])
async def summaries(body: IdsIn, request: Request, me: Principal = Depends(FROM_ORDER_INVENTORY)) -> dict[str, Any]:
    return {"items": await svc(request).summaries(body.ids)}


@router.get("/internal/email-lists", tags=["internal"])
async def internal_email_lists(request: Request, me: Principal = Depends(FROM_NOTIFICATION)) -> dict[str, Any]:
    """notification-svc: who gets staff emails (registration, order, invoice, cancellation, lowStock)."""
    return await svc(request).email_lists()


@router.get("/internal/fees", tags=["internal"])
async def internal_fees(request: Request, me: Principal = Depends(FROM_ORDER)) -> dict[str, Any]:
    """order-svc: the admin fee added to paid quotes (PRD O15)."""
    return await svc(request).fees()


@router.get("/internal/places", tags=["internal"])
async def places(
    request: Request,
    kind: Literal["site", "location", "shelf"] | None = None,
    site: str | None = None,
    location: str | None = None,
    barcode: str | None = None,
    me: Principal = Depends(FROM_INVENTORY),
) -> dict[str, Any]:
    filters = {"kind": kind, "site": site, "location": location, "barcode": barcode}
    return {"items": await svc(request).places(filters)}


@router.put("/internal/places", tags=["internal"])
async def put_place(body: PlaceIn, request: Request, me: Principal = Depends(FROM_INVENTORY)) -> dict[str, Any]:
    return await svc(request).put_place(me, body.model_dump())
