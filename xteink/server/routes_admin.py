"""``/api/devices``, ``/api/firmware``, ``/api/keys`` and ``/api/whoami`` routes (main app only).

Raw device/API keys appear only in the register/rotate/create responses.
"""

from __future__ import annotations

import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from xteink.core import ValidationError
from xteink.core.fwimage import MAX_IMAGE_SIZE, FirmwareImageError, validate

from .auth import Operator, Services, get_services, require_operator

devices_router = APIRouter(
    prefix="/api/devices", tags=["devices"], dependencies=[Depends(require_operator)]
)
firmware_router = APIRouter(
    prefix="/api/firmware", tags=["firmware"], dependencies=[Depends(require_operator)]
)
keys_router = APIRouter(prefix="/api/keys", tags=["keys"], dependencies=[Depends(require_operator)])
whoami_router = APIRouter(prefix="/api", tags=["session"])


class DeviceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    mirror: bool = False


class MirrorUpdate(BaseModel):
    mirror: bool


class QueueRequest(BaseModel):
    item_id: int


class KeyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)


# --- devices ---------------------------------------------------------------


@devices_router.get("")
def list_devices(services: Services = Depends(get_services)) -> dict:
    return {"devices": [asdict(d) for d in services.devices.list()]}


@devices_router.post("", status_code=201)
def register_device(body: DeviceCreate, services: Services = Depends(get_services)) -> dict:
    """Register a device. The raw device key is returned once, here only."""
    device, raw = services.devices.register(body.name, mirror=body.mirror)
    return {"device": asdict(device), "key": raw}


@devices_router.get("/{device_id}")
def device_status(device_id: int, services: Services = Depends(get_services)) -> dict:
    return asdict(services.devices.status(device_id))


@devices_router.post("/{device_id}/revoke")
def revoke_device(device_id: int, services: Services = Depends(get_services)) -> dict:
    return asdict(services.devices.revoke_key(device_id))


@devices_router.post("/{device_id}/rotate")
def rotate_device_key(device_id: int, services: Services = Depends(get_services)) -> dict:
    """Replace the device key; the new raw key is returned once."""
    raw = services.devices.rotate_key(device_id)
    return {"device": asdict(services.devices.get(device_id)), "key": raw}


@devices_router.put("/{device_id}/mirror")
def set_mirror(
    device_id: int, body: MirrorUpdate, services: Services = Depends(get_services)
) -> dict:
    return asdict(services.devices.set_mirror(device_id, body.mirror))


@devices_router.get("/{device_id}/queue")
def device_queue(
    device_id: int,
    state: Literal["queued", "delivered", "all"] = "queued",
    services: Services = Depends(get_services),
) -> dict:
    entries = services.devices.queue(device_id, state=None if state == "all" else state)
    return {"entries": [asdict(e) for e in entries]}


@devices_router.post("/{device_id}/queue", status_code=201)
def queue_item(
    device_id: int, body: QueueRequest, services: Services = Depends(get_services)
) -> dict:
    return asdict(services.devices.queue_item(device_id, body.item_id))


# --- firmware --------------------------------------------------------------


class OfferRequest(BaseModel):
    """Offer an image to one device (``device_id``) or to every provisioned one (``all``)."""

    device_id: int | None = None
    all: bool = False
    dry_run: bool = False


def _image_error(exc: FirmwareImageError) -> JSONResponse:
    status = 413 if exc.code == "too_large" else 422
    return JSONResponse(status_code=status, content={"detail": str(exc), "code": exc.code})


def _validate_bytes(data: bytes):
    # fwimage validates a path; the temp file is removed before returning.
    with tempfile.TemporaryDirectory(prefix="xteink-fw-") as tmp:
        path = Path(tmp) / "image.bin"
        path.write_bytes(data)
        return validate(path)


@firmware_router.get("")
def list_firmware(services: Services = Depends(get_services)) -> dict:
    return {"firmware": [asdict(f) for f in services.firmware.list()]}


@firmware_router.post("", status_code=201, responses={200: {"description": "dry run or known"}})
async def upload_firmware(
    response: Response,
    file: UploadFile = File(...),
    fork_commit: str | None = Form(None),
    source_pr: str | None = Form(None),
    version: str | None = Form(None),
    dry_run: bool = Form(False),
    services: Services = Depends(get_services),
):
    """Validate (ESP header, chip, board tag) and store a firmware image.

    The version is read from the image; ``version`` is required only when the image carries
    none, and overrides it otherwise. With ``dry_run`` the image is validated and nothing is
    stored.
    """
    data = await file.read(MAX_IMAGE_SIZE + 1)
    try:
        info = await run_in_threadpool(_validate_bytes, data)
    except FirmwareImageError as exc:
        return _image_error(exc)
    chosen = (version or "").strip() or info.version
    if not chosen:
        return JSONResponse(
            status_code=422,
            content={
                "detail": "the image carries no version string; pass version explicitly",
                "code": "version_required",
            },
        )
    image = {"size": info.size, "board": info.board, "chip_id": info.chip_id, "version": chosen}
    if dry_run:
        response.status_code = 200
        return {"dry_run": True, "image": image}
    # Hashing, the blob write and SQLite (30 s busy timeout) stay off the event loop.
    result = await run_in_threadpool(
        services.firmware.add,
        data,
        version=chosen,
        board=info.board or "x4",
        fork_commit=fork_commit,
        source_pr=source_pr,
    )
    if not result.created:
        response.status_code = 200
    return {"firmware": asdict(result.firmware), "created": result.created, "image": image}


@firmware_router.get("/{firmware_id}")
def get_firmware(firmware_id: int, services: Services = Depends(get_services)) -> dict:
    return asdict(services.firmware.get(firmware_id))


@firmware_router.get("/{firmware_id}/rollbacks")
def firmware_rollbacks(firmware_id: int, services: Services = Depends(get_services)) -> dict:
    """Devices that rolled this image back (read-only; used by the release flow)."""
    return {"rollbacks": services.firmware.rollbacks_of(firmware_id)}


@firmware_router.post("/{firmware_id}/offer")
def offer_firmware(
    firmware_id: int, body: OfferRequest, services: Services = Depends(get_services)
) -> dict:
    """Offer an image to one device or all. A revoked device, or one that rolled this image
    back, is refused (single: 422) or skipped (``all``). ``dry_run`` reports without writing."""
    if body.all == (body.device_id is not None):
        raise ValidationError("give exactly one of device_id or all")
    fw = services.firmware.get(firmware_id)
    if body.all:
        if body.dry_run:
            offered, revoked, rolled = [], [], []
            for d in services.devices.list():
                if d.revoked_at:
                    revoked.append(d.id)
                elif any(r.id == firmware_id for r in services.firmware.rolled_back(d.id)):
                    rolled.append(d.id)
                else:
                    offered.append(d.id)
        else:
            res = services.firmware.offer_all(firmware_id)
            offered, revoked, rolled = (
                list(res.offered),
                list(res.skipped_revoked),
                list(res.skipped_rolled_back),
            )
        return {
            "firmware": asdict(fw),
            "dry_run": body.dry_run,
            "offered": offered,
            "skipped_revoked": revoked,
            "skipped_rolled_back": rolled,
        }
    device_id = int(body.device_id)  # type: ignore[arg-type]
    if body.dry_run:
        dev = services.devices.get(device_id)
        if dev.revoked_at:
            raise ValidationError(f"device {device_id} is revoked")
        if any(r.id == firmware_id for r in services.firmware.rolled_back(device_id)):
            raise ValidationError(
                f"device {device_id} rolled back firmware {firmware_id} ({fw.version});"
                " it is not offered again"
            )
    else:
        services.firmware.offer(device_id, firmware_id)
    return {"firmware": asdict(fw), "dry_run": body.dry_run, "offered": [device_id]}


# --- keys ------------------------------------------------------------------


@keys_router.get("")
def list_keys(services: Services = Depends(get_services)) -> dict:
    return {"keys": [asdict(k) for k in services.keys.list()]}


@keys_router.post("", status_code=201)
def create_key(body: KeyCreate, services: Services = Depends(get_services)) -> dict:
    """Create an API key. The raw key is returned once, here only."""
    api_key, raw = services.keys.create(body.name)
    return {"api_key": asdict(api_key), "key": raw}


@keys_router.post("/{key_id}/revoke", status_code=204)
def revoke_key(key_id: int, services: Services = Depends(get_services)) -> Response:
    services.keys.revoke(key_id)
    return Response(status_code=204)


# --- whoami ----------------------------------------------------------------


@whoami_router.get("/whoami")
def whoami(operator: Operator = Depends(require_operator)) -> dict:
    """How this request authenticated: ``via`` is ``key`` (the key's name) or ``access``
    (the Cloudflare Access identity, normally an email)."""
    return {"via": operator.via, "identity": operator.identity}
