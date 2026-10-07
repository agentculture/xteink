"""Service wiring and auth dependencies shared by both apps.

* :func:`require_operator` - guards every main-app ``/api`` route. Accepts a non-device
  ``xtk_`` API key, or, only when the main app was built with an Access verifier, a verified
  Cloudflare Access JWT in ``Cf-Access-Jwt-Assertion`` (see :mod:`xteink.server.access`).
* :func:`require_device_key` - ``xtd_`` device keys; guards every device-app route. Never
  looks at Access JWTs.

Both raise 401 (with ``WWW-Authenticate: Bearer``) for missing or bad credentials. Raw keys
and tokens are never echoed back or logged.

Main-app credential order:

1. Any ``Authorization`` header decides on its own: a valid ``Bearer xtk_...`` key is an
   operator, anything else is a 401 (exactly the pre-Access behaviour). It is never swapped
   for an Access JWT on the same request.
2. Otherwise, with Access configured, the ``Cf-Access-Jwt-Assertion`` header is verified.
   Only the header is read, never the ``CF_Authorization`` cookie: Cloudflare adds the header
   to every request it proxies through Access, so the cookie would add nothing but an
   ambient credential on paths that never crossed Access.
3. An Access-authenticated unsafe request (not GET/HEAD/OPTIONS) must also carry
   ``X-Xteink-Request`` (403 otherwise). SSO is an ambient browser credential; a custom
   header cannot be sent cross-site without a CORS preflight, which this app never grants.
"""

from __future__ import annotations

import logging
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

from .access import ACCESS_HEADER, CSRF_HEADER, AccessVerifier, VerificationError

log = logging.getLogger("xteink.server.access")
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


@dataclass(frozen=True)
class Operator:
    """Who is driving the main app: ``via`` is ``key`` or ``access``."""

    via: str
    identity: str
    api_key: ApiKey | None = None


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


def _api_key(creds: HTTPAuthorizationCredentials | None, services: Services) -> ApiKey:
    raw = _token(creds)
    try:
        return services.keys.authenticate(raw)
    except AuthError:
        raise _unauthorized() from None


def _access_operator(request: Request, verifier: AccessVerifier, assertion: str) -> Operator:
    where = f"{request.method} {request.url.path}"
    try:
        ident = verifier.verify(assertion.strip())
    except VerificationError as exc:
        log.warning("access jwt refused (%s) on %s", exc.reason, where)
        raise _unauthorized() from None
    if request.method not in _SAFE_METHODS and not request.headers.get(CSRF_HEADER):
        log.warning(
            "access request without %s refused on %s (%s)", CSRF_HEADER, where, ident.identity
        )
        raise HTTPException(status_code=403, detail=f"{CSRF_HEADER} header required")
    log.info("access: %s via %s on %s", ident.identity, ident.kind, where)
    return Operator("access", ident.identity)


def require_operator(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    services: Services = Depends(get_services),
) -> Operator:
    """An API key (``Authorization: Bearer xtk_...``) or, if configured, a Cloudflare Access JWT."""
    if "authorization" in request.headers:
        key = _api_key(creds, services)
        return Operator("key", key.name, key)
    verifier: AccessVerifier | None = getattr(request.app.state, "access", None)
    assertion = request.headers.get(ACCESS_HEADER)
    if verifier is None or assertion is None:
        raise _unauthorized()
    return _access_operator(request, verifier, assertion)


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
