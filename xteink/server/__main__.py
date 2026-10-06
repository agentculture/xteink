"""``python -m xteink.server``: run both apps, or mint the first API key.

``create-key`` writes straight through :class:`~xteink.core.KeyService` so the
first key can be created without already holding one.
"""

from __future__ import annotations

import argparse
import sys

from . import load_config


def _create_key(name: str) -> int:
    from xteink.core import KeyService, Store

    _, raw = KeyService(Store()).create(name)
    print(raw)  # shown once; only its hash is stored
    print("store this key now; it cannot be shown again", file=sys.stderr)
    return 0


def _serve() -> int:
    try:
        cfg = load_config()
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    try:
        from .app import serve
    except ImportError as exc:
        print(
            f"error: server dependencies missing ({exc}); install xteink[server]",
            file=sys.stderr,
        )
        return 2
    serve(cfg)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m xteink.server", description="xteink HTTP server"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("serve", help="run the main app and the device app")
    ck = sub.add_parser("create-key", help="create an API key and print it once")
    ck.add_argument("name", help="label for the key")
    args = parser.parse_args(argv)
    if args.command == "create-key":
        return _create_key(args.name)
    return _serve()


if __name__ == "__main__":
    sys.exit(main())
