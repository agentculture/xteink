"""Entry point for ``python -m xteink``."""

from __future__ import annotations

import sys

from xteink.cli import main

if __name__ == "__main__":
    sys.exit(main())
