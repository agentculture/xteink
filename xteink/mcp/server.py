"""The MCP server (official ``mcp`` SDK, low-level ``Server`` + ``mcp.types``).

Transports: stdio, and streamable-http. There is no auth layer of its own: the server talks to
the HTTP API with the key from ``XTEINK_API_KEY`` (issue 1 scope is LAN/tailnet/mesh only; this
is never routed through the tunnel).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from xteink import client as api_client
from xteink.mcp import tools

__all__ = ["ServerExtraMissing", "build_server", "run_http", "run_stdio"]


class ServerExtraMissing(ImportError):
    """The ``server`` extra (mcp SDK) is not installed."""


_EXTRA_MESSAGE = "the MCP server needs the 'server' extra: pip install 'xteink[server]'"


def _sdk():
    try:
        import mcp.types as types  # noqa: PLC0415 - optional extra
        from mcp.server.lowlevel import Server  # noqa: PLC0415
    except ImportError as exc:
        raise ServerExtraMissing(_EXTRA_MESSAGE) from exc
    return Server, types


def build_server(client_factory: Callable[[], Any] | None = None):
    server_cls, types = _sdk()
    factory = client_factory or api_client.from_env
    server = server_cls("xteink")

    @server.list_tools()
    async def _list() -> list[Any]:
        return [types.Tool(**spec) for spec in tools.tool_specs()]

    @server.call_tool()
    async def _call(name: str, arguments: dict[str, Any] | None) -> list[Any]:
        import anyio  # noqa: PLC0415

        try:
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

    manager = StreamableHTTPSessionManager(app=build_server())

    @contextlib.asynccontextmanager
    async def lifespan(_app):
        async with manager.run():
            yield

    app = Starlette(routes=[Mount("/mcp", app=manager.handle_request)], lifespan=lifespan)
    uvicorn.run(app, host=bind, port=port, log_level="info")
