"""Tool specs and handlers. Pure API-client calls; no SDK imports and no library logic."""

from __future__ import annotations

import base64
import binascii
from typing import Any

from xteink.client import ApiError, Client, ConfigError

__all__ = ["ToolError", "call_tool", "tool_specs"]

_KIND = {"type": "string", "enum": ["book", "article"]}
_DEVICE = {
    "type": ["string", "integer"],
    "description": "device id or name (see list_devices via the API)",
}

_SPECS: list[dict[str, Any]] = [
    {
        "name": "push_file",
        "description": (
            "Add a file to the xteink library (EPUB, BMP, TXT; Markdown/HTML are converted to "
            "EPUB). Give either `path` (a file on the MCP host) or `content` (text, e.g. a "
            "Markdown article) with `filename`. Pass `device` to queue it for that device."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "file path on the MCP host"},
                "content": {"type": "string", "description": "file text (e.g. Markdown)"},
                "content_base64": {"type": "string", "description": "binary file, base64"},
                "filename": {"type": "string", "description": "e.g. article.md (with content)"},
                "title": {"type": "string"},
                "author": {"type": "string"},
                "kind": _KIND,
                "device": _DEVICE,
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "list_library",
        "description": "List or search library items (title/author search with q).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "q": {"type": "string"},
                "kind": _KIND,
                "limit": {"type": "integer", "minimum": 1, "maximum": 1000},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "send_to_device",
        "description": "Queue a library item for a device so it downloads on its next sync.",
        "inputSchema": {
            "type": "object",
            "properties": {"device": _DEVICE, "item_id": {"type": "integer"}},
            "required": ["device", "item_id"],
            "additionalProperties": False,
        },
    },
]


class ToolError(Exception):
    """A failed tool call; the message is shown to the calling model."""


def tool_specs() -> list[dict[str, Any]]:
    return [dict(s) for s in _SPECS]


def _resolve_device(client: Client, device: str | int) -> int:
    devices = client.list_devices()
    ref = str(device).strip()
    for d in devices:
        if str(d["id"]) == ref:
            return d["id"]
    named = [d for d in devices if d["name"] == ref]
    if len(named) == 1:
        return named[0]["id"]
    if not named:
        raise ToolError(f"unknown_device: no device with id or name {ref!r}")
    raise ToolError(f"ambiguous_device: several devices are named {ref!r}; use the id")


def _brief(item: dict) -> dict:
    keys = ("id", "title", "author", "kind", "format", "size")
    return {k: item[k] for k in keys if k in item}


def _push_file(client: Client, a: dict) -> dict:
    given = [k for k in ("path", "content", "content_base64") if a.get(k) is not None]
    if len(given) != 1:
        raise ToolError("invalid_arguments: give exactly one of path, content, content_base64")
    kw = {k: a[k] for k in ("title", "kind") if a.get(k) is not None}
    kw["author"] = a.get("author") or ""
    if "path" in given:
        try:
            res = client.upload(path=a["path"], filename=a.get("filename") or "", **kw)
        except OSError as exc:
            raise ToolError(f"unreadable_path: {exc.strerror or exc}") from None
    else:
        if not a.get("filename"):
            raise ToolError("invalid_arguments: filename is required with content")
        if "content" in given:
            data = a["content"].encode("utf-8")
        else:
            try:
                data = base64.b64decode(a["content_base64"], validate=True)
            except (binascii.Error, ValueError):
                raise ToolError("invalid_arguments: content_base64 is not valid base64") from None
        res = client.upload(data, a["filename"], **kw)
    out = {"item": _brief(res["item"]), "created": res["created"]}
    if a.get("device") is not None:
        device_id = _resolve_device(client, a["device"])
        out["queued"] = client.queue_item(device_id, res["item"]["id"])
    return out


def call_tool(name: str, arguments: dict[str, Any] | None, client_factory: Any) -> Any:
    args = dict(arguments or {})
    try:
        client = client_factory()
        if name == "push_file":
            return _push_file(client, args)
        if name == "list_library":
            items = client.list_library(args.get("q"), args.get("kind"), args.get("limit", 100))
            return {"items": [_brief(i) for i in items]}
        if name == "send_to_device":
            device_id = _resolve_device(client, args["device"])
            return client.queue_item(device_id, args["item_id"])
    except ApiError as exc:
        raise ToolError(f"{exc.code} (HTTP {exc.status}): {exc.detail}") from None
    except ConfigError as exc:
        raise ToolError(f"missing_key: {exc}") from None
    raise ToolError(f"unknown tool {name!r}")
