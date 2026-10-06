"""HTTP server: a main (LAN) app and a device-only app sharing the core services.

This module is pure stdlib so configuration and the ``create-key`` bootstrap work
without the ``server`` extra; FastAPI is imported only by :mod:`xteink.server.app`.

Two apps, two ports. The Cloudflare tunnel for remote device sync points at the
device app's port only, so remote exposure is limited by port rather than by
path rules: the device app does not mount library/admin routes at all.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

BIND_ENV = "XTEINK_BIND"
PORT_ENV = "XTEINK_PORT"
DEVICE_PORT_ENV = "XTEINK_DEVICE_PORT"

# Bind all interfaces by default so LAN/tailnet readers can reach the server.
# Intentional LAN default (bandit B104); override with XTEINK_BIND=127.0.0.1 to go local-only.
DEFAULT_BIND = "0.0.0.0"  # nosec B104
DEFAULT_PORT = 8780
DEFAULT_DEVICE_PORT = 8781


@dataclass(frozen=True)
class ServerConfig:
    bind: str = DEFAULT_BIND
    port: int = DEFAULT_PORT
    device_port: int = DEFAULT_DEVICE_PORT


def _port(env: Mapping[str, str], name: str, default: int) -> int:
    raw = (env.get(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f"{name} must be an integer port, got {raw!r}") from None
    if not 1 <= value <= 65535:
        raise ValueError(f"{name} must be between 1 and 65535, got {value}")
    return value


def load_config(env: Mapping[str, str] | None = None) -> ServerConfig:
    """Read bind address and ports from the environment (``os.environ`` by default)."""
    env = os.environ if env is None else env
    bind = (env.get(BIND_ENV) or "").strip() or DEFAULT_BIND
    port = _port(env, PORT_ENV, DEFAULT_PORT)
    device_port = _port(env, DEVICE_PORT_ENV, DEFAULT_DEVICE_PORT)
    if port == device_port:
        raise ValueError(f"{PORT_ENV} and {DEVICE_PORT_ENV} must differ (both {port})")
    return ServerConfig(bind=bind, port=port, device_port=device_port)


__all__ = [
    "BIND_ENV",
    "DEFAULT_BIND",
    "DEFAULT_DEVICE_PORT",
    "DEFAULT_PORT",
    "DEVICE_PORT_ENV",
    "PORT_ENV",
    "ServerConfig",
    "load_config",
]
