"""Device protocol v1 routes (mounted under ``/api/device`` on the device app).

The contract the firmware implements is ``docs/device-protocol.md``; keep the two in step.
The parent router in :mod:`xteink.server.app` already enforces the device key, so auth
(401) is checked before the protocol version (426).

Mirror deletes use no server-side tombstones: the device reports its inventory of
server-delivered files in ``POST /status``; the inventory is held **in memory per
process** (per app) and keyed by device id. After a server restart it is empty until the
device's next ``POST /status``, which the protocol requires at the start of every sync.
"""

from __future__ import annotations

import re
import threading
from dataclasses import asdict
from typing import Iterator

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from xteink.core import Device, NotFoundError, ValidationError

from .auth import Services, get_services, require_device_key

PROTOCOL_VERSION = "1"
SUPPORTED_VERSIONS = (PROTOCOL_VERSION,)
PROTOCOL_HEADER = "X-Xteink-Protocol"
SD_SAFETY_MARGIN = 1024 * 1024  # bytes kept free on the SD card (1 MiB)
CHUNK = 64 * 1024

_SHA256 = r"^[0-9a-f]{64}$"
_RANGE = re.compile(r"^bytes=(\d*)-(\d*)$")
_MEDIA_TYPES = {
    "epub": "application/epub+zip",
    "pdf": "application/pdf",
    "txt": "text/plain; charset=utf-8",
}


def require_protocol(
    x_xteink_protocol: str | None = Header(default=None, alias=PROTOCOL_HEADER),
) -> str:
    """426 Upgrade Required unless the request speaks a supported protocol version."""
    if x_xteink_protocol not in SUPPORTED_VERSIONS:
        got = "missing" if x_xteink_protocol is None else repr(x_xteink_protocol)
        raise HTTPException(
            status_code=426,
            detail={
                "message": (
                    f"unsupported device protocol ({PROTOCOL_HEADER} {got}); "
                    f"this server speaks {PROTOCOL_HEADER}: {', '.join(SUPPORTED_VERSIONS)}"
                ),
                "supported": list(SUPPORTED_VERSIONS),
            },
            headers={"Upgrade": f"xteink-device/{PROTOCOL_VERSION}"},
        )
    return x_xteink_protocol


router = APIRouter(dependencies=[Depends(require_protocol)])


# --- models -----------------------------------------------------------------


class InventoryEntry(BaseModel):
    sha256: str = Field(..., pattern=_SHA256)
    unmodified: bool


class StatusReport(BaseModel):
    free_sd_bytes: int | None = Field(default=None, ge=0)
    firmware_version: str | None = Field(default=None, max_length=200)
    last_error: str | None = Field(default=None, max_length=2000)
    last_sync_result: str | None = Field(default=None, max_length=200)
    inventory: list[InventoryEntry] | None = None


class Ack(BaseModel):
    item_id: int
    sha256: str = Field(..., pattern=_SHA256)


# --- per-process inventory ----------------------------------------------------


class _Inventories:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_device: dict[int, list[InventoryEntry]] = {}

    def set(self, device_id: int, entries: list[InventoryEntry]) -> None:
        with self._lock:
            self._by_device[device_id] = list(entries)

    def get(self, device_id: int) -> list[InventoryEntry]:
        with self._lock:
            return list(self._by_device.get(device_id, []))


_INIT_LOCK = threading.Lock()


def _inventories(request: Request) -> _Inventories:
    state = request.app.state
    if getattr(state, "device_inventories", None) is None:
        with _INIT_LOCK:
            if getattr(state, "device_inventories", None) is None:
                state.device_inventories = _Inventories()
    return state.device_inventories


def _public(device: Device) -> dict:
    d = asdict(device)
    d.pop("key_id", None)
    return d


def _missing_shas(services: Services, shas: list[str]) -> set[str]:
    """The subset of ``shas`` with no item in the library."""
    if not shas:
        return set()
    with services.store.connect() as c:
        return {
            s
            for s in shas
            if c.execute("SELECT 1 FROM items WHERE sha256 = ?", (s,)).fetchone() is None
        }


# --- routes -------------------------------------------------------------------


@router.post("/status")
def post_status(
    body: StatusReport,
    request: Request,
    device: Device = Depends(require_device_key),
    services: Services = Depends(get_services),
) -> dict:
    """Device status at the start (and end) of each sync; replaces the last report."""
    updated = services.devices.report_status(
        device.id,
        last_sync_result=body.last_sync_result,
        free_sd_bytes=body.free_sd_bytes,
        firmware_version=body.firmware_version,
        last_error=body.last_error,
    )
    if body.inventory is not None:
        _inventories(request).set(device.id, body.inventory)
    return {"protocol": PROTOCOL_VERSION, "device": _public(updated)}


@router.get("/queue")
def get_queue(
    request: Request,
    device: Device = Depends(require_device_key),
    services: Services = Depends(get_services),
) -> dict:
    """Items to download, items skipped (sd_full), and mirror delete instructions."""
    budget = None
    if device.free_sd_bytes is not None:
        budget = device.free_sd_bytes - SD_SAFETY_MARGIN
    items, skipped = [], []
    for entry in services.devices.queue(device.id, state="queued"):
        if budget is not None and entry.size > budget:
            skipped.append({"id": entry.item_id, "reason": "sd_full"})
            continue
        if budget is not None:
            budget -= entry.size
        items.append(
            {
                "id": entry.item_id,
                "title": entry.title,
                "size": entry.size,
                "sha256": entry.sha256,
                "format": services.library.get(entry.item_id).format,
                "url": f"/api/device/items/{entry.item_id}",
            }
        )
    deletes: list[dict] = []
    if device.mirror:
        unmodified = [e.sha256 for e in _inventories(request).get(device.id) if e.unmodified]
        unmodified = list(dict.fromkeys(unmodified))
        missing = _missing_shas(services, unmodified)
        deletes = [{"sha256": s} for s in unmodified if s in missing]
    return {"protocol": PROTOCOL_VERSION, "items": items, "skipped": skipped, "deletes": deletes}


def _parse_range(header: str, size: int) -> tuple[int, int] | None:
    """``(start, end)`` inclusive, or None if unsatisfiable/unsupported (-> 416)."""
    m = _RANGE.match(header.strip())
    if m is None or (not m.group(1) and not m.group(2)):
        return None
    first, last = m.group(1), m.group(2)
    if not first:  # suffix range: last N bytes
        n = int(last)
        if n == 0 or size == 0:
            return None
        return max(size - n, 0), size - 1
    start = int(first)
    end = size - 1 if not last else min(int(last), size - 1)
    if start >= size or (last and int(last) < start):
        return None
    return start, end


def _iter_file(path, start: int, length: int) -> Iterator[bytes]:
    with open(path, "rb") as f:
        f.seek(start)
        remaining = length
        while remaining > 0:
            chunk = f.read(min(CHUNK, remaining))
            if not chunk:
                return
            remaining -= len(chunk)
            yield chunk


@router.get("/items/{item_id}")
def download_item(
    item_id: int,
    range_header: str | None = Header(default=None, alias="Range"),
    device: Device = Depends(require_device_key),
    services: Services = Depends(get_services),
) -> Response:
    """The item's bytes; supports a single ``Range: bytes=...`` for resume."""
    if not any(e.item_id == item_id for e in services.devices.queue(device.id, state=None)):
        raise NotFoundError(f"item {item_id} is not queued for this device")
    item = services.library.get(item_id)
    path = services.library.file_path(item_id)
    size = item.size
    headers = {"Accept-Ranges": "bytes", "ETag": f'"{item.sha256}"'}
    media = _MEDIA_TYPES.get(item.format, "application/octet-stream")
    if range_header is None:
        headers["Content-Length"] = str(size)
        return StreamingResponse(_iter_file(path, 0, size), media_type=media, headers=headers)
    span = _parse_range(range_header, size)
    if span is None:
        return Response(
            status_code=416,
            content=b"",
            headers={**headers, "Content-Range": f"bytes */{size}"},
        )
    start, end = span
    length = end - start + 1
    headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    headers["Content-Length"] = str(length)
    return StreamingResponse(
        _iter_file(path, start, length), status_code=206, media_type=media, headers=headers
    )


@router.post("/ack")
def ack(
    body: Ack,
    device: Device = Depends(require_device_key),
    services: Services = Depends(get_services),
) -> dict:
    """Confirm a download by its sha256; the queue entry becomes ``delivered``."""
    try:
        entry = services.devices.mark_delivered(device.id, body.item_id, body.sha256)
    except ValidationError as exc:
        raise HTTPException(status_code=409, detail=f"{exc}; re-download the item") from None
    return {
        "protocol": PROTOCOL_VERSION,
        "id": entry.item_id,
        "state": entry.state,
        "delivered_at": entry.delivered_at,
    }
