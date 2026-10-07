"""FastAPI apps: the main LAN app and the device-only app (what the tunnel targets).

* :func:`create_app` - ``/api/library*``, ``/api/devices*``, ``/api/keys*``, ``/api/whoami``
  (API key, or a verified Cloudflare Access JWT when built with ``access=``) and the web UI
  at ``/`` (open on the LAN; Cloudflare Access fronts it through the tunnel).
* :func:`create_device_app` - only ``/api/device/*`` (device key; never an Access JWT). Every
  other path, including ``/docs`` and ``/openapi.json``, is a 404 because nothing else is
  mounted.

Device routes extension point: if a module ``xteink.server.routes_device`` exists and
defines ``router`` (an :class:`fastapi.APIRouter` with paths relative to
``/api/device``), it is mounted on the device app under ``/api/device`` behind
:func:`~xteink.server.auth.require_device_key`.
"""

from __future__ import annotations

import asyncio
import importlib
import importlib.util
import json
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from xteink.core import AuthError, Device, NotFoundError, Store, ValidationError

from . import ServerConfig
from .access import AccessVerifier
from .auth import ServicesHolder, require_device_key
from .routes_admin import devices_router, keys_router, whoami_router
from .routes_library import router as library_router

API_VERSION = "1"
WEBASSETS_DIR = Path(__file__).parent / "_webassets"
DEVICE_PREFIX = "/api/device"
DEVICE_ROUTES_MODULE = "xteink.server.routes_device"

_DESCRIPTION = (
    "xteink library server API. Every /api route needs `Authorization: Bearer xtk_...`. "
    "When the server is configured for Cloudflare Access (XTEINK_ACCESS_TEAM_DOMAIN + "
    "XTEINK_ACCESS_AUD), a request without an Authorization header may instead carry the "
    "`Cf-Access-Jwt-Assertion` header Cloudflare adds at the edge; unsafe methods then also "
    "need `X-Xteink-Request: 1`."
)

_PLACEHOLDER = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>xteink</title></head>
<body><h1>xteink</h1><p>The xteink server is running. The web UI is not installed yet;
the HTTP API is under <code>/api/</code> (see <a href="/docs">/docs</a>).</p></body></html>
"""


def _install_error_handlers(app: FastAPI) -> None:
    def not_found(_: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    def invalid(_: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    def unauthorized(_: Request, __: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=401,
            content={"detail": "invalid or missing key"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    app.add_exception_handler(NotFoundError, not_found)
    app.add_exception_handler(ValidationError, invalid)
    app.add_exception_handler(AuthError, unauthorized)


def create_app(
    store: Store | None = None,
    *,
    webassets_dir: Path | None = None,
    services: ServicesHolder | None = None,
    access: AccessVerifier | None = None,
) -> FastAPI:
    """The main (LAN/tailnet) app. Every ``/api`` route requires an API key, or, when
    ``access`` is given, a Cloudflare Access JWT that ``access`` verifies."""
    app = FastAPI(title="xteink", version=API_VERSION, description=_DESCRIPTION)
    app.state.services = services or ServicesHolder(store)
    app.state.access = access
    _install_error_handlers(app)
    app.include_router(library_router)
    app.include_router(devices_router)
    app.include_router(keys_router)
    app.include_router(whoami_router)

    web = WEBASSETS_DIR if webassets_dir is None else Path(webassets_dir)
    if (web / "index.html").is_file():
        app.mount("/", _CachedStaticFiles(directory=web, html=True), name="web")
    else:

        @app.get("/", include_in_schema=False, response_class=HTMLResponse)
        def placeholder() -> str:
            return _PLACEHOLDER

    return app


class _CachedStaticFiles(StaticFiles):
    """Serve the SPA so a deploy is picked up on the next load.

    ``index.html`` (and the ``/`` alias) revalidates every time; Vite's
    content-hashed files under ``assets/`` never change, so they cache for a year.
    Without this, browsers cache ``index.html`` heuristically and keep showing the
    previous UI after a deploy.
    """

    async def get_response(self, path, scope):  # type: ignore[override]
        response = await super().get_response(path, scope)
        if path.startswith("assets/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            response.headers["Cache-Control"] = "no-cache"
        return response


def _device_router() -> APIRouter:
    router = APIRouter(
        prefix=DEVICE_PREFIX, tags=["device"], dependencies=[Depends(require_device_key)]
    )

    @router.get("/whoami")
    def whoami(device: Device = Depends(require_device_key)) -> dict:
        return {"id": device.id, "name": device.name}

    if importlib.util.find_spec(DEVICE_ROUTES_MODULE) is not None:
        extra = importlib.import_module(DEVICE_ROUTES_MODULE)
        router.include_router(extra.router)
    return router


def create_device_app(
    store: Store | None = None, *, services: ServicesHolder | None = None
) -> FastAPI:
    """The device-only app. Mounts nothing but ``/api/device/*``; no docs, no schema."""
    app = FastAPI(
        title="xteink device API",
        version=API_VERSION,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.services = services or ServicesHolder(store)
    _install_error_handlers(app)
    app.include_router(_device_router())
    return app


def create_apps(
    store: Store | None = None, *, access: AccessVerifier | None = None
) -> tuple[FastAPI, FastAPI]:
    """Both apps over one shared set of services (one Store). ``access`` goes to the main
    app only; the device app accepts device keys and nothing else."""
    holder = ServicesHolder(store)
    return create_app(services=holder, access=access), create_device_app(services=holder)


def build_apps(cfg: ServerConfig) -> tuple[FastAPI, FastAPI]:
    """The apps ``serve`` runs: an Access verifier only when Access is configured.

    Building the verifier makes no network call; the JWKS is fetched on the first request
    that carries an Access JWT.
    """
    access = cfg.access.verifier() if cfg.access is not None else None
    return create_apps(access=access)


def render_openapi() -> str:
    """The main app's OpenAPI schema as committed in ``api/openapi.json``."""
    schema = create_app(webassets_dir=Path("/nonexistent")).openapi()
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"


async def _serve_both(cfg: ServerConfig) -> None:
    import uvicorn

    main_app, device_app = build_apps(cfg)
    servers = [
        uvicorn.Server(uvicorn.Config(main_app, host=cfg.bind, port=cfg.port)),
        uvicorn.Server(uvicorn.Config(device_app, host=cfg.bind, port=cfg.device_port)),
    ]
    await asyncio.gather(*(s.serve() for s in servers))


def serve(cfg: ServerConfig) -> None:  # pragma: no cover - blocking network server
    asyncio.run(_serve_both(cfg))


__all__ = [
    "API_VERSION",
    "build_apps",
    "create_app",
    "create_apps",
    "create_device_app",
    "render_openapi",
    "serve",
]
