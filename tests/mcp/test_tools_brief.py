"""MCP results keep the item size the API returns (field ``size``)."""

from xteink.mcp.tools import _brief


def test_brief_keeps_api_size_field():
    item = {"id": 1, "title": "T", "author": "", "kind": "book", "format": "txt", "size": 42}
    assert _brief(item)["size"] == 42
