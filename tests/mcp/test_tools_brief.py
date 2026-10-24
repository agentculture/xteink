"""MCP results keep the item size the API returns (field ``size``)."""

from xteink.mcp.tools import _brief


def test_brief_keeps_api_size_field():
    item = {"id": 1, "title": "T", "author": "", "kind": "book", "format": "txt", "size": 42}
    assert _brief(item)["size"] == 42


def test_kind_enum_has_the_four_kinds():
    from xteink.mcp.tools import tool_specs

    specs = {t["name"]: t for t in tool_specs()}
    for name in ("push_file", "list_library"):
        enum = specs[name]["inputSchema"]["properties"]["kind"]["enum"]
        assert enum == ["book", "article", "transcript", "newspaper"]
    assert "set_kind" not in specs
