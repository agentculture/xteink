"""``xteink tunnel`` — remote-access status and a dry-run plan (no Cloudflare API calls).

``status`` probes the two public hostnames over HTTPS; ``plan`` only *prints* the two
``cultureflare remote-login`` commands and never executes them.
"""

from __future__ import annotations

import argparse
import os
from typing import Any

from xteink.cli._commands.overview import emit_overview
from xteink.cli._commands.server import add_json, json_mode, probe
from xteink.cli._errors import EXIT_ENV_ERROR
from xteink.cli._output import emit_result

DEFAULT_UI_HOST = "ebooks.culture.dev"
DEFAULT_DEVICE_HOST = "xteink.culture.dev"
DEFAULT_UI_PORT = 8780
DEFAULT_DEVICE_PORT = 8781


def _hosts(args: argparse.Namespace) -> tuple[str, str]:
    ui = getattr(args, "ui_host", None) or os.environ.get("XTEINK_UI_HOST") or DEFAULT_UI_HOST
    dev = (
        getattr(args, "device_host", None)
        or os.environ.get("XTEINK_DEVICE_HOST")
        or DEFAULT_DEVICE_HOST
    )
    return ui, dev


def _classify(kind: str, status: int | None, why: str) -> dict[str, Any]:
    if status is None:
        return {"status": "unreachable", "error": why}
    ok = status == 401 if kind == "device" else status in (301, 302, 303, 307, 308, 401, 403)
    out: dict[str, Any] = {"status": "reachable" if ok else "unexpected", "http_status": status}
    if not ok:
        out["note"] = (
            "expected 401 (key-gated)"
            if kind == "device"
            else "expected a Cloudflare Access redirect/login (3xx/401/403)"
        )
    return out


def cmd_status(args: argparse.Namespace) -> int:
    ui, dev = _hosts(args)
    ui_url, dev_url = f"https://{ui}/", f"https://{dev}/api/device/whoami"
    rep = {
        "ui": {"host": ui, **_classify("ui", *probe(ui_url))},
        "device": {"host": dev, **_classify("device", *probe(dev_url))},
    }
    if json_mode(args):
        emit_result(rep, json_mode=True)
    else:
        emit_result(
            "\n".join(
                f"{k}: {v['host']} — {v['status']}"
                + (f" ({v['error']})" if "error" in v else "")
                + (f" [{v['note']}]" if "note" in v else "")
                for k, v in rep.items()
            ),
            json_mode=False,
        )
    down = any(v["status"] != "reachable" for v in rep.values())
    return EXIT_ENV_ERROR if (down and args.strict) else 0


def build_plan(args: argparse.Namespace) -> dict[str, Any]:
    ui, dev = _hosts(args)
    allow = args.allow or os.environ.get("XTEINK_OWNER_EMAIL") or "OWNER_EMAIL"
    base = "cultureflare remote-login setup"
    return {
        "dry_run": True,
        "commands": [
            f"{base} --hostname {ui} --service http://127.0.0.1:{args.ui_port} "
            f"--allow {allow} --shushu",
            f"{base} --hostname {dev} --service http://127.0.0.1:{args.device_port} "
            "--no-access --shushu",
        ],
        "note": "xteink prints these and never runs them. cultureflare is dry-run until "
        "you add --apply to each command yourself.",
    }


def cmd_plan(args: argparse.Namespace) -> int:
    plan = build_plan(args)
    if json_mode(args):
        emit_result(plan, json_mode=True)
    else:
        emit_result("\n".join([*plan["commands"], "", f"note: {plan['note']}"]), json_mode=False)
    return 0


def cmd_overview(args: argparse.Namespace) -> int:
    emit_overview(
        "xteink tunnel",
        [
            {
                "title": "Verbs",
                "items": [
                    "status — probe the public UI and device hostnames (no Cloudflare API)",
                    "plan — print the two cultureflare remote-login commands (never runs them)",
                    "overview — this description",
                ],
            },
            {
                "title": "Configuration",
                "items": [
                    f"XTEINK_UI_HOST (default {DEFAULT_UI_HOST})",
                    f"XTEINK_DEVICE_HOST (default {DEFAULT_DEVICE_HOST})",
                    "XTEINK_OWNER_EMAIL (used by plan --allow)",
                ],
            },
        ],
        json_mode=json_mode(args),
    )
    return 0


def _host_flags(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--ui-host", help=f"UI hostname (env XTEINK_UI_HOST, default {DEFAULT_UI_HOST})."
    )
    p.add_argument(
        "--device-host",
        help=f"Device hostname (env XTEINK_DEVICE_HOST, default {DEFAULT_DEVICE_HOST}).",
    )


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("tunnel", help="Remote access via Cloudflare Tunnel (status, plan).")
    add_json(p)
    p.set_defaults(func=cmd_overview, json=False)
    nsub = p.add_subparsers(dest="tunnel_command", parser_class=type(p))

    st = nsub.add_parser("status", help="Probe the two public hostnames.")
    add_json(st)
    _host_flags(st)
    st.add_argument("--strict", action="store_true", help="Exit 2 if anything is not reachable.")
    st.set_defaults(func=cmd_status)

    pl = nsub.add_parser("plan", help="Print the cultureflare commands (dry-run, never executed).")
    add_json(pl)
    _host_flags(pl)
    pl.add_argument("--allow", help="Owner email for Cloudflare Access (env XTEINK_OWNER_EMAIL).")
    pl.add_argument("--ui-port", type=int, default=DEFAULT_UI_PORT)
    pl.add_argument("--device-port", type=int, default=DEFAULT_DEVICE_PORT)
    pl.set_defaults(func=cmd_plan)

    ov = nsub.add_parser("overview", help="Describe the tunnel noun.")
    add_json(ov)
    ov.set_defaults(func=cmd_overview)
