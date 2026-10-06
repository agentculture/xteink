"""``xteink device`` — list, queue and revoke devices via the HTTP API (thin client).

``queue`` and ``revoke`` are dry-run unless ``--apply`` is given: they print what they would
do and send no write request (reads used to resolve names are fine).
"""

from __future__ import annotations

import argparse
from typing import Any

from xteink import client as api
from xteink.cli._commands.device_usb import register_usb
from xteink.cli._commands.overview import emit_overview
from xteink.cli._commands.server import add_json, call, json_mode, make_client
from xteink.cli._errors import EXIT_USER_ERROR, CliError
from xteink.cli._output import emit_result

DRY_RUN_HINT = "dry-run: nothing changed; re-run with --apply to do it."


def resolve_device(client: api.Client, ref: str) -> dict[str, Any]:
    """Resolve a device id or (case-insensitive) name to its API record."""
    devices = call(client.list_devices)
    if ref.strip().isdigit():
        for d in devices:
            if d["id"] == int(ref):
                return d
    matches = [d for d in devices if d["name"].lower() == ref.strip().lower()]
    if len(matches) == 1:
        return matches[0]
    known = ", ".join(f"{d['id']}={d['name']}" for d in devices) or "none registered"
    if len(matches) > 1:
        raise CliError(EXIT_USER_ERROR, f"device name {ref!r} is ambiguous", f"use an id: {known}")
    raise CliError(EXIT_USER_ERROR, f"no device matches {ref!r}", f"known devices: {known}")


def short(d: dict[str, Any]) -> dict[str, Any]:
    return {"id": d["id"], "name": d["name"]}


def _emit(args: argparse.Namespace, payload: dict[str, Any], text: str) -> None:
    emit_result(payload if json_mode(args) else text, json_mode=json_mode(args))


def cmd_list(args: argparse.Namespace) -> int:
    devices = call(make_client().list_devices)
    if json_mode(args):
        emit_result({"devices": devices}, json_mode=True)
        return 0
    lines = [
        f"{d['id']}\t{d['name']}\t{'REVOKED' if d.get('revoked_at') else 'active'}"
        f"\tlast seen: {d.get('last_seen') or 'never'}"
        for d in devices
    ]
    emit_result("\n".join(lines) or "no devices registered", json_mode=False)
    return 0


def cmd_queue(args: argparse.Namespace) -> int:
    client = make_client()
    dev = resolve_device(client, args.device)
    item = call(lambda: client.get_item(args.item_id))
    what = f"queue item {item['id']} ({item['title']!r}) for device {dev['id']} ({dev['name']})"
    payload = {
        "action": "queue",
        "applied": bool(args.apply),
        "device": short(dev),
        "item": {"id": item["id"], "title": item["title"]},
    }
    if not args.apply:
        _emit(args, payload, f"would {what}\n{DRY_RUN_HINT}")
        return 0
    payload["entry"] = call(lambda: client.queue_item(dev["id"], item["id"]))
    _emit(args, payload, f"queued: {what}")
    return 0


def cmd_revoke(args: argparse.Namespace) -> int:
    client = make_client()
    dev = resolve_device(client, args.device)
    what = f"revoke the key of device {dev['id']} ({dev['name']})"
    payload = {"action": "revoke", "applied": bool(args.apply), "device": short(dev)}
    if not args.apply:
        _emit(args, payload, f"would {what}\n{DRY_RUN_HINT}")
        return 0
    payload["result"] = call(lambda: client.revoke_device(int(dev["id"])))
    _emit(args, payload, f"revoked: {what}")
    return 0


def cmd_overview(args: argparse.Namespace) -> int:
    emit_overview(
        "xteink device",
        [
            {
                "title": "Verbs",
                "items": [
                    "list — registered devices",
                    "queue DEVICE ITEM_ID [--apply] — queue a library item for a device",
                    "revoke DEVICE [--apply] — revoke a device key",
                    "backup --port PORT [--apply] — dump the flash over USB (esptool)",
                    "provision --port PORT [--apply] — send Wi-Fi/URLs/key over USB",
                    "overview — this description",
                ],
            },
            {
                "title": "Safety",
                "items": [
                    "DEVICE is an id or a name",
                    "queue/revoke are dry-run until --apply is given",
                ],
            },
        ],
        json_mode=json_mode(args),
    )
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("device", help="Devices: list, queue, revoke (see 'device overview').")
    add_json(p)
    p.set_defaults(func=cmd_overview, json=False)
    nsub = p.add_subparsers(dest="device_command", parser_class=type(p))

    ls = nsub.add_parser("list", help="List registered devices.")
    add_json(ls)
    ls.set_defaults(func=cmd_list)

    q = nsub.add_parser("queue", help="Queue a library item for a device (dry-run by default).")
    q.add_argument("device", metavar="DEVICE", help="Device id or name.")
    q.add_argument("item_id", metavar="ITEM_ID", type=int, help="Library item id.")
    q.add_argument("--apply", action="store_true", help="Actually queue it.")
    add_json(q)
    q.set_defaults(func=cmd_queue)

    r = nsub.add_parser("revoke", help="Revoke a device key (dry-run by default).")
    r.add_argument("device", metavar="DEVICE", help="Device id or name.")
    r.add_argument("--apply", action="store_true", help="Actually revoke.")
    add_json(r)
    r.set_defaults(func=cmd_revoke)

    register_usb(nsub)  # backup / provision (USB; see device_usb.py)

    ov = nsub.add_parser("overview", help="Describe the device noun.")
    add_json(ov)
    ov.set_defaults(func=cmd_overview)
