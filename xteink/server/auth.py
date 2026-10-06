"""Service wiring and bearer-key auth dependencies shared by both apps.

* :func:`require_api_key` - non-device ``xtk_`` keys; guards every main-app ``/api`` route.
* :func:`require_device_key` - ``xtd_`` device keys; guards every device-app route.

Both raise 401 (with ``WWW-Authenticate: Bearer``) for a missing, malformed, unknown,
revoked or wrong-kind key. Raw keys are never echoed back or logged.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from xteink.core import (
    ApiKey,
    AuthError,
    Device,
    DeviceService,
    KeyService,
    LibraryService,
    Store,
)


@dataclass(frozen=True)
class Services:
    store: Store
    library: LibraryService
    devices: DeviceService
    keys: KeyService

    @classmethod
    def from_store(cls, store: Store) -> "Services":
        return cls(store, LibraryService(store), DeviceService(store), KeyService(store))


class ServicesHolder:
    """Builds :class:`Services` on first use so creating an app touches no disk."""

    def __init__(self, store: Store | None = None) -> None:
        self._store = store
        self._services: Services | None = None
        self._lock = threading.Lock()

    def get(self) -> Services:
        if self._services is None:
            with self._lock:
                if self._services is None:
                    self._services = Services.from_store(self._store or Store())
        return self._services


def get_services(request: Request) -> Services:
    return request.app.state.services.get()


_bearer = HTTPBearer(auto_error=False, description="API key (xtk_...) or device key (xtd_...)")


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=401, detail="invalid or missing key", headers={"WWW-Authenticate": "Bearer"}
    )


def _token(creds: HTTPAuthorizationCredentials | None) -> str:
    if creds is None or creds.scheme.lower() != "bearer" or not creds.credentials.strip():
        raise _unauthorized()
    return creds.credentials.strip()


def require_api_key(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    services: Services = Depends(get_services),
) -> ApiKey:
    """Authenticate a non-device API key (``Authorization: Bearer xtk_...``)."""
    raw = _token(creds)
    try:
        return services.keys.authenticate(raw)
    except AuthError:
        raise _unauthorized() from None


def require_device_key(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    services: Services = Depends(get_services),
) -> Device:
    """Authenticate a device key (``Authorization: Bearer xtd_...``); returns the Device."""
    raw = _token(creds)
    try:
        return services.devices.authenticate(raw)
    except AuthError:
        raise _unauthorized() from None
