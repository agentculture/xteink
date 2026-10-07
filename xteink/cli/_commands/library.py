"""``xteink library`` — add, list and remove library items via the HTTP API (thin client).

``add`` and ``rm`` are dry-run unless ``--apply`` is given.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from xteink.cli._commands.device import DRY_RUN_HINT, resolve_device, short
from xteink.cli._commands.overview import emit_overview
from xteink.cli._commands.server import add_json, call, json_mode, make_client
from xteink.cli._errors import EXIT_USER_ERROR, CliError
from xteink.cli._output import emit_result

KINDS = ("book", "article", "image")


def _emit(args: argparse.Namespace, payload: dict[str, Any], text: str) -> None:
    emit_result(payload if json_mode(args) else text, json_mode=json_mode(args))


def _line(i: dict[str, Any]) -> str:
    by = f" — {i['author']}" if i.get("author") else ""
    return f"{i['id']}\t{i['kind']}\t{i['title']}{by}\t({i['format']}, {i['size']} bytes)"


def cmd_list(args: argparse.Namespace) -> None:
    client = make_client()
    items = call(lambda: client.list_library(args.q, args.kind, args.limit))
    if json_mode(args):
        emit_result({"items": items}, json_mode=True)
    else:
        emit_result("\n".join(_line(i) for i in items) or "library is empty", json_mode=False)


def cmd_add(args: argparse.Namespace) -> None:
    path = Path(args.path)
    if not path.is_file():
        raise CliError(EXIT_USER_ERROR, f"not a file: {path}", "pass the path of a local book file")
    client = make_client()
    dev = resolve_device(client, args.device) if args.device else None
    size = path.stat().st_size
    what = f"upload {path.name} ({size} bytes)"
    if args.title:
        what += f" titled {args.title!r}"
    if dev:
        what += f", then queue it for device {dev['id']} ({dev['name']})"
    payload: dict[str, Any] = {
        "action": "add",
        "applied": bool(args.apply),
        "file": str(path),
        "size": size,
        "device": short(dev) if dev else None,
    }
    if not args.apply:
        _emit(args, payload, f"would {what}\n{DRY_RUN_HINT}")
        return
    res = call(
        lambda: client.upload(
            title=args.title, author=args.author or "", kind=args.kind, path=str(path)
        )
    )
    payload.update(item=res["item"], created=res["created"])
    text = f"{'added' if res['created'] else 'already in library'}: {_line(res['item'])}"
    if dev:
        payload["entry"] = call(lambda: client.queue_item(dev["id"], res["item"]["id"]))
        text += f"\nqueued for device {dev['id']} ({dev['name']})"
    _emit(args, payload, text)


def cmd_rm(args: argparse.Namespace) -> None:
    client = make_client()
    item = call(lambda: client.get_item(args.item_id))
    what = f"remove library item {item['id']} ({item['title']!r})"
    payload = {
        "action": "rm",
        "applied": bool(args.apply),
        "item": {"id": item["id"], "title": item["title"]},
    }
    if not args.apply:
        _emit(args, payload, f"would {what}\n{DRY_RUN_HINT}")
        return
    call(lambda: client.delete_item(item["id"]))
    _emit(args, payload, f"removed: {what}")


def cmd_overview(args: argparse.Namespace) -> None:
    emit_overview(
        "xteink library",
        [
            {
                "title": "Verbs",
                "items": [
                    "list [--q --kind --limit] — list or search items",
                    "add PATH [--title --author --kind --device ID|NAME] [--apply] — upload a file "
                    "(and optionally queue it)",
                    "rm ID [--apply] — remove an item",
                    "overview — this description",
                ],
            },
            {"title": "Safety", "items": ["add/rm are dry-run until --apply is given"]},
        ],
        json_mode=json_mode(args),
    )


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("library", help="Library: add, list, rm (see 'library overview').")
    add_json(p)
    p.set_defaults(func=cmd_overview, json=False)
    nsub = p.add_subparsers(dest="library_command", parser_class=type(p))

    ls = nsub.add_parser("list", help="List or search library items.")
    ls.add_argument("--q", help="Search title/author.")
    ls.add_argument("--kind", choices=KINDS)
    ls.add_argument("--limit", type=int, default=100)
    add_json(ls)
    ls.set_defaults(func=cmd_list)

    a = nsub.add_parser("add", help="Upload a file (dry-run by default).")
    a.add_argument("path", metavar="PATH", help="Local file to upload.")
    a.add_argument("--title")
    a.add_argument("--author")
    a.add_argument("--kind", choices=KINDS)
    a.add_argument("--device", help="Also queue the item for this device (id or name).")
    a.add_argument("--apply", action="store_true", help="Actually upload.")
    add_json(a)
    a.set_defaults(func=cmd_add)

    r = nsub.add_parser("rm", help="Remove an item (dry-run by default).")
    r.add_argument("item_id", metavar="ID", type=int)
    r.add_argument("--apply", action="store_true", help="Actually remove.")
    add_json(r)
    r.set_defaults(func=cmd_rm)

    ov = nsub.add_parser("overview", help="Describe the library noun.")
    add_json(ov)
    ov.set_defaults(func=cmd_overview)
