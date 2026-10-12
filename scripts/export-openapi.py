#!/usr/bin/env python3
"""Export the main app's OpenAPI schema to ``api/openapi.json``.

Usage:
    uv run python scripts/export-openapi.py            # (re)write api/openapi.json
    uv run python scripts/export-openapi.py --check    # exit 1 if the file is stale
    uv run python scripts/export-openapi.py --output PATH

Needs the ``server`` extra (``uv sync --extra server``). The drift check also runs as
``tests/server/test_app_openapi.py``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = REPO_ROOT / "api" / "openapi.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true", help="fail if the file is stale")
    args = parser.parse_args(argv)
    try:
        from xteink.server.app import render_openapi
    except ImportError as exc:
        print(f"error: {exc}; run `uv sync --extra server`", file=sys.stderr)
        return 2
    rendered = render_openapi()
    if args.check:
        current = args.output.read_text() if args.output.is_file() else ""
        if current != rendered:
            print(f"{args.output} is stale; run scripts/export-openapi.py", file=sys.stderr)
            return 1
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered)
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
