"""``python -m xteink.mcp`` - serve xteink tools over stdio (default) or streamable-http."""

from __future__ import annotations

import argparse
import os
import sys

from xteink import client
from xteink.mcp import server

DEFAULT_MCP_BIND = "0.0.0.0"  # nosec B104 - LAN/tailnet service by design
DEFAULT_MCP_PORT = 8782


def main(argv: list[str] | None = None, env: dict[str, str] | None = None) -> int:
    env = dict(os.environ) if env is None else env
    p = argparse.ArgumentParser(prog="python -m xteink.mcp", description=__doc__)
    p.add_argument("--http", action="store_true", help="streamable-http instead of stdio")
    p.add_argument("--bind", default=env.get("XTEINK_MCP_BIND") or DEFAULT_MCP_BIND)
    p.add_argument("--port", type=int, default=int(env.get("XTEINK_MCP_PORT") or DEFAULT_MCP_PORT))
    args = p.parse_args(argv)
    use_http = args.http or (env.get("XTEINK_MCP_TRANSPORT") or "").lower() in ("http", "https")
    try:
        client.from_env(env)  # fail fast, with a clear message, when no key is configured
        if use_http:
            server.run_http(args.bind, args.port)
        else:
            server.run_stdio()
    except client.ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except server.ServerExtraMissing as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
