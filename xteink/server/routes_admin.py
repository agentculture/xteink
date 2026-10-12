"""``/api/devices``, ``/api/keys`` and ``/api/whoami`` routes (main app only).

Raw device/API keys appear only in the register/rotate/create responses.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field

from .auth import Operator, Services, get_services, require_operator

devices_router = APIRouter(
    prefix="/api/devices", tags=["devices"], dependencies=[Depends(require_operator)]
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
