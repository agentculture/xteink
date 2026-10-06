"""``/api/library`` routes (main app only). Every upload goes through ``ingest_and_add``."""

from __future__ import annotations

import re
from dataclasses import asdict
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse

from xteink.core.ingest import (
    DEFAULT_LIMITS,
    IngestEnvironmentError,
    IngestError,
    ingest_and_add,
)

from .auth import Services, get_services, require_api_key

router = APIRouter(prefix="/api/library", tags=["library"], dependencies=[Depends(require_api_key)])

UPLOAD_LIMITS = DEFAULT_LIMITS

_STATUS_BY_CODE = {
    "too_large": 413,
    "unsupported_format": 415,
    "pdf_not_supported": 415,
}
_MEDIA_TYPES = {
    "epub": "application/epub+zip",
    "bmp": "image/bmp",
    "txt": "text/plain; charset=utf-8",
}
_UNSAFE_FILENAME = re.compile(r"[^\w .()\-]+")

Kind = Literal["book", "article"]


def _ingest_error_response(exc: IngestError) -> JSONResponse:
    if isinstance(exc, IngestEnvironmentError):
        status = 503
    else:
        status = _STATUS_BY_CODE.get(exc.code, 422)
    return JSONResponse(status_code=status, content={"detail": str(exc), "code": exc.code})


@router.get("")
def list_items(
    q: str | None = Query(None, description="search title/author"),
    kind: Kind | None = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    services: Services = Depends(get_services),
) -> dict:
    """List items (optionally by kind) or search them with ``q``."""
    if q is not None and q.strip():
        items = services.library.search(q, limit=limit)
        if kind is not None:
            items = [i for i in items if i.kind == kind]
    else:
        items = services.library.list(kind=kind, limit=limit, offset=offset)
    return {"items": [asdict(i) for i in items]}


@router.post("", status_code=201, responses={200: {"description": "already in the library"}})
async def upload_item(
    response: Response,
    file: UploadFile = File(...),
    title: str | None = Form(None),
    author: str = Form(""),
    kind: Kind | None = Form(None),
    services: Services = Depends(get_services),
):
    """Upload a book/article (EPUB, BMP, TXT, or Markdown/HTML converted to EPUB)."""
    # Read at most one byte past the cap so oversize uploads fail without buffering it all.
    data = await file.read(UPLOAD_LIMITS.max_bytes + 1)
    try:
        # pandoc conversion can take seconds; keep it off the event loop.
        result = await run_in_threadpool(
            ingest_and_add,
            services.library,
            data,
            filename=file.filename or "",
            title=title,
            author=author,
            kind=kind,
            limits=UPLOAD_LIMITS,
        )
    except IngestError as exc:
        return _ingest_error_response(exc)
    if not result.created:
        response.status_code = 200
    return {"item": asdict(result.item), "created": result.created}


@router.get("/{item_id}")
def get_item(item_id: int, services: Services = Depends(get_services)) -> dict:
    return asdict(services.library.get(item_id))


@router.get("/{item_id}/file", response_class=FileResponse)
def download_item(item_id: int, services: Services = Depends(get_services)):
    item = services.library.get(item_id)
    path = services.library.file_path(item_id)
    stem = _UNSAFE_FILENAME.sub("_", item.title).strip(" ._") or f"item-{item.id}"
    return FileResponse(
        path,
        media_type=_MEDIA_TYPES.get(item.format, "application/octet-stream"),
        filename=f"{stem[:120]}.{item.format}",
    )


@router.delete("/{item_id}", status_code=204)
def delete_item(item_id: int, services: Services = Depends(get_services)) -> Response:
    services.library.delete(item_id)
    return Response(status_code=204)
