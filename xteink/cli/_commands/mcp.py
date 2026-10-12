"""``xteink mcp serve`` — run the MCP server (delegates to :mod:`xteink.mcp`).

``xteink.mcp`` is imported lazily inside the handler so the CLI's module import graph stays
stdlib-only; this is the one sanctioned lazy import of ``xteink.mcp`` from the CLI.
"""

from __future__ import annotations

import argparse

from xteink.cli._commands.overview import emit_overview
from xteink.cli._commands.server import add_json, json_mode
from xteink.cli._errors import EXIT_ENV_ERROR, CliError

INSTALL_HINT = "pip install 'xteink[server]'"


def cmd_serve(args: argparse.Namespace) -> int:
    try:
        from xteink.mcp.__main__ import main as mcp_main  # lazy: keeps CLI imports stdlib-only
    except ImportError as exc:
        raise CliError(
            EXIT_ENV_ERROR, f"the MCP server is unavailable: {exc}", INSTALL_HINT
        ) from None
    argv: list[str] = []
    if args.http:
        argv.append("--http")
    if args.bind:
        argv += ["--bind", args.bind]
    if args.port is not None:
        argv += ["--port", str(args.port)]
    try:
        return int(mcp_main(argv))
    except ImportError as exc:  # SDK missing at run time
        raise CliError(EXIT_ENV_ERROR, f"the MCP SDK is unavailable: {exc}", INSTALL_HINT) from None


def cmd_overview(args: argparse.Namespace) -> int:
    emit_overview(
        "xteink mcp",
        [
            {
                "title": "Verbs",
                "items": [
                    "serve [--http] [--bind ADDR] [--port N] — serve MCP tools over stdio "
                    "(default) or streamable-http",
                    "overview — this description",
                ],
            },
            {
                "title": "Requirements",
                "items": [f"needs the server extra: {INSTALL_HINT}", "needs XTEINK_API_KEY"],
            },
        ],
        json_mode=json_mode(args),
    )
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("mcp", help="MCP server (see 'mcp overview').")
    add_json(p)
    p.set_defaults(func=cmd_overview, json=False)
    nsub = p.add_subparsers(dest="mcp_command", parser_class=type(p))
    s = nsub.add_parser("serve", help="Run the MCP server.")
    s.add_argument("--http", action="store_true", help="streamable-http instead of stdio.")
    s.add_argument("--bind", help="HTTP bind address (env XTEINK_MCP_BIND).")
    s.add_argument("--port", type=int, help="HTTP port (env XTEINK_MCP_PORT).")
    add_json(s)  # accepted for rubric uniformity; stdio carries the MCP protocol, not CLI JSON
    s.set_defaults(func=cmd_serve)
    ov = nsub.add_parser("overview", help="Describe the mcp noun.")
    add_json(ov)
    ov.set_defaults(func=cmd_overview)
