"""``xteink firmware`` — upload, list and offer device firmware via the HTTP API (thin client).

``release`` and ``report-rollbacks`` (the agent release flow) live in ``firmware_release``.

``upload`` and ``offer`` are dry-run unless ``--apply`` is given. A dry-run still asks the
server to validate the image (or check the offer) but stores / offers nothing.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from xteink.cli._commands.device import DRY_RUN_HINT, resolve_device, short
from xteink.cli._commands.firmware_release import register_release
from xteink.cli._commands.overview import emit_overview
from xteink.cli._commands.server import add_json, call, json_mode, make_client
from xteink.cli._errors import EXIT_USER_ERROR, CliError
from xteink.cli._output import emit_result


def _emit(args: argparse.Namespace, payload: dict[str, Any], text: str) -> None:
    emit_result(payload if json_mode(args) else text, json_mode=json_mode(args))


def _line(f: dict[str, Any]) -> str:
    extra = []
    if f.get("fork_commit"):
        extra.append(f"commit {f['fork_commit']}")
    if f.get("source_pr"):
        extra.append(f"pr {f['source_pr']}")
    tail = f"\t({', '.join(extra)})" if extra else ""
    return f"{f['id']}\t{f['version']}\t{f['board']}\t{f['size']} bytes{tail}"


def resolve_firmware(client: Any, ref: str) -> dict[str, Any]:
    """Resolve a firmware id or (exact) version string to its API record."""
    items = call(client.list_firmware)
    ref = ref.strip()
    if ref.isdigit():
        for f in items:
            if f["id"] == int(ref):
                return f
    matches = [f for f in items if f["version"] == ref]
    if len(matches) == 1:
        return matches[0]
    known = ", ".join(f"{f['id']}={f['version']}" for f in items) or "none uploaded"
    if len(matches) > 1:
        raise CliError(
            EXIT_USER_ERROR, f"firmware version {ref!r} is ambiguous", f"use an id: {known}"
        )
    raise CliError(EXIT_USER_ERROR, f"no firmware matches {ref!r}", f"known firmware: {known}")


def cmd_list(args: argparse.Namespace) -> None:
    items = call(make_client().list_firmware)
    if json_mode(args):
        emit_result({"firmware": items}, json_mode=True)
    else:
        emit_result("\n".join(_line(f) for f in items) or "no firmware uploaded", json_mode=False)


def cmd_upload(args: argparse.Namespace) -> None:
    path = Path(args.image)
    if not path.is_file():
        raise CliError(EXIT_USER_ERROR, f"not a file: {path}", "pass the path of a firmware .bin")
    client = make_client()

    def send(dry_run: bool) -> dict[str, Any]:
        return call(
            lambda: client.upload_firmware(
                path,
                fork_commit=args.commit,
                source_pr=args.pr,
                version=args.version,
                dry_run=dry_run,
            )
        )

    res = send(dry_run=not args.apply)  # a bad image fails here (exit 1) either way
    image = res["image"]
    payload: dict[str, Any] = {
        "action": "upload",
        "applied": bool(args.apply),
        "file": str(path),
        "image": image,
        "fork_commit": args.commit,
        "source_pr": args.pr,
    }
    what = (
        f"store {path.name} as firmware {image['version']} "
        f"({image['size']} bytes, board {image.get('board') or 'untagged'}, "
        f"commit {args.commit}, pr {args.pr})"
    )
    if not args.apply:
        _emit(args, payload, f"image is valid; would {what}\n{DRY_RUN_HINT}")
        return
    payload.update(firmware=res["firmware"], created=res["created"])
    word = "stored" if res["created"] else "already stored"
    _emit(args, payload, f"{word}: {_line(res['firmware'])}")


def cmd_offer(args: argparse.Namespace) -> None:
    client = make_client()
    fw = resolve_firmware(client, args.firmware)
    dev = resolve_device(client, args.device) if args.device else None
    target = f"device {dev['id']} ({dev['name']})" if dev else "every provisioned device"
    payload: dict[str, Any] = {
        "action": "offer",
        "applied": bool(args.apply),
        "firmware": {"id": fw["id"], "version": fw["version"]},
        "device": short(dev) if dev else None,
        "all": bool(args.all),
    }
    # The server answers a dry run without writing; a rolled-back or revoked device is a 422.
    res = call(
        lambda: client.offer_firmware(
            fw["id"],
            device_id=dev["id"] if dev else None,
            all_devices=bool(args.all),
            dry_run=not args.apply,
        )
    )
    payload.update(
        offered=res["offered"],
        skipped_revoked=res.get("skipped_revoked", []),
        skipped_rolled_back=res.get("skipped_rolled_back", []),
    )
    what = f"offer firmware {fw['id']} ({fw['version']}) to {target}"
    extra = ""
    if args.all:
        extra = (
            f"\n{len(payload['offered'])} offered, {len(payload['skipped_revoked'])} revoked "
            f"skipped, {len(payload['skipped_rolled_back'])} rolled-back skipped"
        )
    if not args.apply:
        _emit(args, payload, f"would {what}{extra}\n{DRY_RUN_HINT}")
        return
    _emit(args, payload, f"offered: {what}{extra}")


def cmd_rollbacks(args: argparse.Namespace) -> None:
    client = make_client()
    fw = resolve_firmware(client, args.firmware)
    items = call(lambda: client.firmware_rollbacks(fw["id"]))
    payload = {"firmware": {"id": fw["id"], "version": fw["version"]}, "rollbacks": items}
    text = "\n".join(f"{r['device_id']}\t{r['device_name']}\t{r['rolled_back_at']}" for r in items)
    _emit(args, payload, text or f"no device rolled back firmware {fw['id']} ({fw['version']})")


def cmd_overview(args: argparse.Namespace) -> None:
    emit_overview(
        "xteink firmware",
        [
            {
                "title": "Verbs",
                "items": [
                    "list — uploaded firmware images",
                    "upload IMAGE --commit SHA --pr URL [--version V] [--apply] — validate and "
                    "store an image",
                    "offer FIRMWARE (--device ID|NAME | --all) [--apply] — offer an image to "
                    "devices (FIRMWARE is an id or version)",
                    "rollbacks FIRMWARE — devices that rolled an image back",
                    "release PR — ship a merged fork PR over the air: build, upload, offer to "
                    "every device, comment on the PR",
                    "report-rollbacks [--dry-run] — comment once on the PR that shipped a build "
                    "a device rolled back",
                    "overview — this description",
                ],
            },
            {
                "title": "Safety",
                "items": [
                    "upload/offer are dry-run until --apply is given",
                    "a bad image exits 1 and stores nothing",
                    "a device that rolled an image back is never offered it again (exit 1)",
                    "release refuses (exit 1) unless the PR is merged into the integration "
                    "branch with green checks; it never flashes over serial",
                ],
            },
        ],
        json_mode=json_mode(args),
    )


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "firmware", help="Firmware: upload, list, offer, release (see 'firmware overview')."
    )
    add_json(p)
    p.set_defaults(func=cmd_overview, json=False)
    nsub = p.add_subparsers(dest="firmware_command", parser_class=type(p))

    ls = nsub.add_parser("list", help="List uploaded firmware images.")
    add_json(ls)
    ls.set_defaults(func=cmd_list)

    u = nsub.add_parser("upload", help="Validate and store an image (dry-run by default).")
    u.add_argument("image", metavar="IMAGE", help="Local firmware .bin.")
    u.add_argument("--commit", required=True, help="Firmware fork commit the image was built from.")
    u.add_argument("--pr", required=True, help="URL of the pull request that produced it.")
    u.add_argument("--version", help="Only needed when the image carries no version string.")
    u.add_argument("--apply", action="store_true", help="Actually store it.")
    add_json(u)
    u.set_defaults(func=cmd_upload)

    o = nsub.add_parser("offer", help="Offer an image to devices (dry-run by default).")
    o.add_argument("firmware", metavar="FIRMWARE", help="Firmware id or version.")
    g = o.add_mutually_exclusive_group(required=True)
    g.add_argument("--device", help="Offer to this device (id or name).")
    g.add_argument("--all", action="store_true", help="Offer to every provisioned device.")
    o.add_argument("--apply", action="store_true", help="Actually offer it.")
    add_json(o)
    o.set_defaults(func=cmd_offer)

    rb = nsub.add_parser("rollbacks", help="List devices that rolled an image back.")
    rb.add_argument("firmware", metavar="FIRMWARE", help="Firmware id or version.")
    add_json(rb)
    rb.set_defaults(func=cmd_rollbacks)

    register_release(nsub)

    ov = nsub.add_parser("overview", help="Describe the firmware noun.")
    add_json(ov)
    ov.set_defaults(func=cmd_overview)
