"""HTTP layer for document-svc: docs/api/documents.openapi.yaml is the contract."""

from __future__ import annotations

from typing import Annotated, Any, Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from cimh_common.auth import Principal
from cimh_common.authz import current_principal, require_service, require_staff
from cimh_common.errors import ProblemError, forbidden

from .service import DocumentService

router = APIRouter()
MAX_LABELS = 200
UploadKind = Literal["supplier_quote", "signed_agreement", "upload", "commercial_invoice"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ReasonIn(Strict):
    reason: str = Field(min_length=3, max_length=500)


class LabelsIn(Strict):
    productId: str = Field(min_length=1, max_length=64)
    productName: str | None = Field(default=None, max_length=200)
    # ~15 ms per QR code (pure-Python encoder): 200 labels ≈ 3 s, rendered off the event loop.
    barcodes: list[Annotated[str, Field(min_length=1, max_length=80)]] = Field(min_length=1, max_length=MAX_LABELS)


def svc(request: Request) -> DocumentService:
    s: DocumentService = request.app.state.documents
    return s


def cid(request: Request) -> str:
    return str(getattr(request.state, "trace_id", "") or "")


def require_inventory_svc(me: Principal = Depends(require_service)) -> Principal:
    if me.sub != "svc:inventory":
        raise forbidden("Only inventory-svc may call this endpoint")
    return me


async def _read_capped(file: UploadFile, limit: int) -> bytes:
    """Read at most limit + 1 bytes: a 2 GB body is refused after 20 MB, not buffered whole."""
    chunks, size = [], 0
    while chunk := await file.read(1024 * 1024):
        size += len(chunk)
        if size > limit:
            raise ProblemError(413, "FILE_TOO_LARGE", f"Files can be at most {limit // (1024 * 1024)} MB")
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("/files", status_code=201, tags=["files"])
async def upload(
    request: Request,
    file: Annotated[UploadFile, File()],
    requestId: Annotated[str, Form(min_length=1, max_length=64, pattern=r"^[0-9A-Za-z_-]+$")],
    kind: Annotated[UploadKind, Form()],
    me: Principal = Depends(current_principal),
) -> dict[str, Any]:
    s = svc(request)
    data = await _read_capped(file, s.max_bytes)
    return await s.upload(me, requestId, kind, file.filename, data, cid(request))


@router.get("/files/{fileId}", tags=["files"])
async def download(
    fileId: str,
    request: Request,
    disposition: Annotated[Literal["inline", "attachment"], Query()] = "inline",
    me: Principal = Depends(current_principal),
) -> Response:
    meta, rel = await svc(request).download(me, fileId)
    name = meta["name"]
    ascii_name = name.encode("ascii", "replace").decode().replace('"', "_").replace("?", "_")
    headers = {
        "Content-Disposition": f"{disposition}; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name)}",
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
    }
    if request.app.state.settings.serve_direct:  # dev only: no nginx in front
        return FileResponse(svc(request).files.root / rel, media_type=meta["mime"], headers=headers)
    headers["X-Accel-Redirect"] = "/_protected/" + rel.removeprefix("protected/")
    return Response(status_code=200, media_type=meta["mime"], headers=headers)


@router.delete("/files/{fileId}", status_code=204, tags=["files"])
async def delete(fileId: str, body: ReasonIn, request: Request, me: Principal = Depends(require_staff)) -> Response:
    await svc(request).delete(me, fileId, body.reason, cid(request))
    return Response(status_code=204)


@router.post("/internal/labels", status_code=201, tags=["internal"])
async def labels(body: LabelsIn, request: Request, me: Principal = Depends(require_inventory_svc)) -> dict[str, Any]:
    return await svc(request).labels(me, body.productId, body.productName, body.barcodes, cid(request))
