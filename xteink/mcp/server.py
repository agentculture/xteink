"""The MCP server (official ``mcp`` SDK, low-level ``Server`` + ``mcp.types``).

Transports:

* stdio: the server talks to the HTTP API with the key from ``XTEINK_API_KEY`` (a local,
  single-user process).
* streamable-http: every request must carry ``Authorization: Bearer xtk_...``; requests
  without one get 401 before reaching the MCP session, and each tool call uses the caller's
  key against the API, which decides. The HTTP server holds no key of its own, and
  ``push_file``'s ``path`` (a file on the MCP host) is refused over HTTP.

Issue 1 scope is LAN/tailnet/mesh only; this is never routed through the tunnel.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from typing import Any

from xteink import client as api_client
from xteink.mcp import tools

__all__ = ["ServerExtraMissing", "build_server", "run_http", "run_stdio"]


class ServerExtraMissing(ImportError):
    """The ``server`` extra (mcp SDK) is not installed."""


_EXTRA_MESSAGE = "the MCP server needs the 'server' extra: pip install 'xteink[server]'"


def _env() -> dict[str, str]:
    return dict(os.environ)


def _sdk():
    try:
        import mcp.types as types  # noqa: PLC0415 - optional extra
        from mcp.server.lowlevel import Server  # noqa: PLC0415
    except ImportError as exc:
        raise ServerExtraMissing(_EXTRA_MESSAGE) from exc
    return Server, types


def _bearer(headers: Any) -> str:
    auth = headers.get("authorization") or ""
    scheme, _, key = auth.partition(" ")
    return key.strip() if scheme.lower() == "bearer" else ""


def build_server(client_factory: Callable[[], Any] | None = None, *, http_auth: bool = False):
    """The MCP server. With ``http_auth`` every tool call uses the HTTP caller's bearer key."""
    server_cls, types = _sdk()
    default_factory = client_factory or api_client.from_env
    server = server_cls("xteink")

    def factory_for_call(arguments: dict[str, Any] | None) -> Callable[[], Any]:
        if not http_auth:
            return default_factory
        if arguments and arguments.get("path") is not None:
            raise tools.ToolError(
                "invalid_arguments: path (a file on the MCP host) is not allowed over HTTP; "
                "send content or content_base64"
            )
        key = _bearer(server.request_context.request.headers)
        if not key:
            raise tools.ToolError("missing_key: send Authorization: Bearer xtk_...")
        base_url = api_client.from_env({**_env(), api_client.KEY_ENV: key}).base_url
        return lambda: api_client.Client(base_url, key)

    @server.list_tools()
    async def _list() -> list[Any]:
        return [types.Tool(**spec) for spec in tools.tool_specs()]

    @server.call_tool()
    async def _call(name: str, arguments: dict[str, Any] | None) -> list[Any]:
        import anyio  # noqa: PLC0415

        try:
            factory = factory_for_call(arguments)
            # urllib is blocking (uploads may wait on pandoc); keep it off the event loop.
            result = await anyio.to_thread.run_sync(tools.call_tool, name, arguments, factory)
        except tools.ToolError as exc:
            raise ValueError(str(exc)) from exc  # the SDK turns this into isError
        return [types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]

    return server


def run_stdio() -> None:
    try:
        import anyio  # noqa: PLC0415
        from mcp.server.stdio import stdio_server  # noqa: PLC0415
    except ImportError as exc:
        raise ServerExtraMissing(_EXTRA_MESSAGE) from exc
    server = build_server()

    async def main() -> None:
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())

    anyio.run(main)


def run_http(bind: str, port: int) -> None:
    try:
        import uvicorn  # noqa: PLC0415
        from mcp.server.streamable_http_manager import (  # noqa: PLC0415
            StreamableHTTPSessionManager,
        )
        from starlette.applications import Starlette  # noqa: PLC0415
        from starlette.routing import Mount  # noqa: PLC0415
    except ImportError as exc:
        raise ServerExtraMissing(_EXTRA_MESSAGE) from exc
    import contextlib  # noqa: PLC0415

    from starlette.responses import JSONResponse  # noqa: PLC0415

    manager = StreamableHTTPSessionManager(app=build_server(http_auth=True))

    async def guarded(scope, receive, send) -> None:
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        if not _bearer(headers).startswith("xtk_"):
            response = JSONResponse(
                {"detail": "send Authorization: Bearer xtk_... (an xteink API key)"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
            await response(scope, receive, send)
            return
        await manager.handle_request(scope, receive, send)

    @contextlib.asynccontextmanager
    async def lifespan(_app):
        async with manager.run():
            yield

    app = Starlette(routes=[Mount("/mcp", app=guarded)], lifespan=lifespan)
    uvicorn.run(app, host=bind, port=port, log_level="info")
