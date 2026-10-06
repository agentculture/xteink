"""``xteink server`` — reachability/health of the xteink HTTP API (a thin API client).

Also hosts the helpers shared by the other API-client nouns (``library``, ``device``,
``tunnel``): client construction, API-error -> :class:`CliError` mapping, and a no-redirect
HTTP probe. The CLI talks to the server only over HTTP via :mod:`xteink.client`; it never
imports ``xteink.core`` or ``xteink.server``.
"""

from __future__ import annotations

import argparse
import os
import urllib.error
import urllib.parse
import urllib.request  # nosec B404 - scheme restricted to http/https in probe()
from typing import Any, Callable, TypeVar

from xteink import client as api
from xteink.cli._commands.overview import emit_overview
from xteink.cli._errors import EXIT_ENV_ERROR, EXIT_USER_ERROR, CliError
from xteink.cli._output import emit_result

T = TypeVar("T")

DEVICE_URL_ENV = "XTEINK_DEVICE_URL"
DEFAULT_DEVICE_URL = "http://127.0.0.1:8781"


def json_mode(args: argparse.Namespace) -> bool:
    return bool(getattr(args, "json", False))


def add_json(p: argparse.ArgumentParser) -> None:
    p.add_argument("--json", action="store_true", help="Emit structured JSON.")


def make_client() -> api.Client:
    try:
        return api.from_env()
    except api.ConfigError as exc:
        raise CliError(
            EXIT_ENV_ERROR,
            str(exc),
            f"set {api.KEY_ENV} (and {api.URL_ENV} if the server is not on {api.DEFAULT_URL})",
        ) from None


def call(fn: Callable[[], T]) -> T:
    """Run an API call, mapping client errors onto the CLI exit-code policy."""
    try:
        return fn()
    except api.ConfigError as exc:
        raise CliError(EXIT_ENV_ERROR, str(exc), f"check {api.URL_ENV} / {api.KEY_ENV}") from None
    except api.ServerUnreachable as exc:
        raise CliError(
            EXIT_ENV_ERROR,
            exc.detail,
            f"start the server, or point {api.URL_ENV} at it ('xteink server status')",
        ) from None
    except api.AuthenticationError as exc:
        raise CliError(
            EXIT_USER_ERROR,
            f"API key rejected ({exc.code}): {exc.detail}",
            f"check {api.KEY_ENV}; mint one with 'python -m xteink.server create-key NAME'",
        ) from None
    except api.ApiError as exc:
        if exc.status >= 500:
            raise CliError(
                EXIT_ENV_ERROR,
                f"server error {exc.status} {exc.code}: {exc.detail}",
                "check the server logs; 503 converter_missing means pandoc is not installed",
            ) from None
        raise CliError(
            EXIT_USER_ERROR,
            f"{exc.status} {exc.code}: {exc.detail}",
            "check the arguments (see 'xteink library list' / 'xteink device list')",
        ) from None


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a: Any, **kw: Any) -> None:  # type: ignore[override]
        return None


def probe(url: str, timeout: float = 5.0) -> tuple[int | None, str]:
    """Unauthenticated GET without following redirects -> ``(status, "")`` or ``(None, why)``."""
    if urllib.parse.urlsplit(url).scheme not in ("http", "https"):
        return None, "not an http(s) URL"
    opener = urllib.request.build_opener(_NoRedirect)
    req = urllib.request.Request(url, method="GET")  # nosec B310
    try:
        with opener.open(req, timeout=timeout) as resp:  # nosec B310
            return resp.status, ""
    except urllib.error.HTTPError as exc:
        return exc.code, ""
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return None, str(getattr(exc, "reason", exc))


def _main_url() -> str:
    return (os.environ.get(api.URL_ENV) or api.DEFAULT_URL).strip().rstrip("/")


def _device_url() -> str:
    return (os.environ.get(DEVICE_URL_ENV) or DEFAULT_DEVICE_URL).strip().rstrip("/")


def build_status() -> dict[str, Any]:
    main_url = _main_url()
    status, why = probe(main_url + "/")
    server: dict[str, Any] = {"url": main_url, "reachable": status is not None}
    if status is None:
        server["error"] = why
    else:
        server["http_status"] = status

    key: dict[str, Any] = {"configured": bool(os.environ.get(api.KEY_ENV, "").strip())}
    if key["configured"] and server["reachable"]:
        try:
            api.from_env().list_library(limit=1)
            key["valid"] = True
        except api.AuthenticationError:
            key["valid"] = False
        except api.ApiError as exc:
            key["valid"] = None
            key["error"] = f"{exc.status} {exc.code}"

    dev_url = _device_url()
    dstatus, dwhy = probe(dev_url + "/api/device/whoami")
    device: dict[str, Any] = {"url": dev_url}
    if dstatus is None:
        device.update(status="unreachable", error=dwhy)
    elif dstatus == 401:
        device["status"] = "alive"
    else:
        device.update(status="unexpected", http_status=dstatus)
    return {"server": server, "api_key": key, "device_app": device}


def render_status(rep: dict[str, Any]) -> str:
    s, k, d = rep["server"], rep["api_key"], rep["device_app"]
    lines = [
        f"server: {s['url']} — "
        + ("reachable" if s["reachable"] else f"UNREACHABLE ({s.get('error', '')})")
    ]
    if not k["configured"]:
        lines.append(f"api key: not configured (set {api.KEY_ENV})")
    elif "valid" not in k:
        lines.append("api key: configured (not checked, server unreachable)")
    elif k["valid"] is None:
        lines.append(f"api key: could not be checked ({k.get('error')})")
    else:
        lines.append("api key: " + ("valid" if k["valid"] else "REJECTED"))
    lines.append(f"device app: {d['url']} — {d['status']}")
    return "\n".join(lines)


def cmd_status(args: argparse.Namespace) -> int:
    rep = build_status()
    emit_result(rep if json_mode(args) else render_status(rep), json_mode=json_mode(args))
    if not rep["server"]["reachable"]:
        return EXIT_ENV_ERROR
    if rep["api_key"].get("valid") is False:
        return EXIT_USER_ERROR
    return 0


def cmd_overview(args: argparse.Namespace) -> int:
    emit_overview(
        "xteink server",
        [
            {
                "title": "Verbs",
                "items": [
                    "status — reachability of the API and device app, and whether the key works",
                    "overview — this description",
                ],
            },
            {
                "title": "Configuration",
                "items": [
                    f"{api.URL_ENV} (default {api.DEFAULT_URL})",
                    f"{api.KEY_ENV} (never printed)",
                    f"{DEVICE_URL_ENV} (default {DEFAULT_DEVICE_URL})",
                ],
            },
        ],
        json_mode=json_mode(args),
    )
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("server", help="API server health (see 'xteink server overview').")
    add_json(p)
    p.set_defaults(func=cmd_overview, json=False)
    nsub = p.add_subparsers(dest="server_command", parser_class=type(p))
    st = nsub.add_parser("status", help="Probe the API, the key and the device app.")
    add_json(st)
    st.set_defaults(func=cmd_status)
    ov = nsub.add_parser("overview", help="Describe the server noun.")
    add_json(ov)
    ov.set_defaults(func=cmd_overview)
