"""Drive `python -m xteink.mcp` (stdio) with the mcp SDK client against the real API."""

import json
import os
import subprocess
import sys

import anyio
import pytest

from xteink.core import DeviceService

pytest.importorskip("mcp")
from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402


def run_session(env_extra, fn):
    env = {**os.environ, **env_extra}
    params = StdioServerParameters(command=sys.executable, args=["-m", "xteink.mcp"], env=env)

    async def go():
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                return await fn(s)

    return anyio.run(go)


def text(res):
    return res.content[0].text


def test_lists_three_tools(api_url, api_key):
    async def fn(s):
        return {t.name for t in (await s.list_tools()).tools}

    names = run_session({"XTEINK_URL": api_url, "XTEINK_API_KEY": api_key}, fn)
    assert names == {"push_file", "list_library", "send_to_device"}


def test_push_markdown_list_and_queue(api_url, api_key, store, device):
    async def fn(s):
        pushed = await s.call_tool(
            "push_file",
            {"content": "# Title\n\nSome article.", "filename": "post.md", "title": "Post"},
        )
        listed = await s.call_tool("list_library", {"kind": "article"})
        item_id = json.loads(text(pushed))["item"]["id"]
        sent = await s.call_tool("send_to_device", {"device": "reader", "item_id": item_id})
        return pushed, listed, sent, item_id

    pushed, listed, sent, item_id = run_session(
        {"XTEINK_URL": api_url, "XTEINK_API_KEY": api_key}, fn
    )
    assert not pushed.isError
    assert json.loads(text(pushed))["item"]["kind"] == "article"
    items = json.loads(text(listed))["items"]
    assert [(i["id"], i["kind"]) for i in items] == [(item_id, "article")]
    assert not sent.isError
    queue = DeviceService(store).queue(device.id)
    assert [e.item_id for e in queue] == [item_id]


def test_push_with_device_queues_in_one_call(api_url, api_key, store, device):
    async def fn(s):
        return await s.call_tool(
            "push_file", {"content": "plain", "filename": "n.txt", "device": str(device.id)}
        )

    res = run_session({"XTEINK_URL": api_url, "XTEINK_API_KEY": api_key}, fn)
    out = json.loads(text(res))
    assert out["queued"]["item_id"] == out["item"]["id"]


def test_push_path(api_url, api_key, tmp_path):
    f = tmp_path / "b.txt"
    f.write_text("book text")

    async def fn(s):
        return await s.call_tool("push_file", {"path": str(f), "title": "B"})

    res = run_session({"XTEINK_URL": api_url, "XTEINK_API_KEY": api_key}, fn)
    assert json.loads(text(res))["item"]["title"] == "B"


def test_invalid_key_is_tool_error_with_code(api_url):
    async def fn(s):
        return await s.call_tool("list_library", {})

    res = run_session({"XTEINK_URL": api_url, "XTEINK_API_KEY": "xtk_bogus"}, fn)
    assert res.isError
    assert "401" in text(res)
    assert "bogus" not in text(res)


def test_unknown_device_and_api_error_mapping(api_url, api_key):
    async def fn(s):
        a = await s.call_tool("send_to_device", {"device": "nope", "item_id": 1})
        b = await s.call_tool("push_file", {"content": "x", "filename": "a.xyz"})
        return a, b

    a, b = run_session({"XTEINK_URL": api_url, "XTEINK_API_KEY": api_key}, fn)
    assert a.isError
    assert "unknown_device" in text(a)
    assert b.isError
    assert "415" in text(b)
    assert "Traceback" not in text(b)


def test_missing_key_refuses_to_start(api_url):
    env = {k: v for k, v in os.environ.items() if k != "XTEINK_API_KEY"}
    r = subprocess.run(
        [sys.executable, "-m", "xteink.mcp"],
        env={**env, "XTEINK_URL": api_url},
        capture_output=True,
        text=True,
        timeout=30,
        stdin=subprocess.DEVNULL,
    )
    assert r.returncode == 2
    assert "XTEINK_API_KEY" in r.stderr


def test_streamable_http_transport(api_url, api_key):
    import socket
    import time

    from mcp.client.streamable_http import streamablehttp_client

    with socket.socket() as sk:
        sk.bind(("127.0.0.1", 0))
        port = sk.getsockname()[1]
    proc = subprocess.Popen(
        [sys.executable, "-m", "xteink.mcp", "--http", "--bind", "127.0.0.1", "--port", str(port)],
        env={**os.environ, "XTEINK_URL": api_url, "XTEINK_API_KEY": api_key},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(100):
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
                break
            except OSError:
                time.sleep(0.1)

        async def go():
            async with streamablehttp_client(f"http://127.0.0.1:{port}/mcp") as (r, w, _):
                async with ClientSession(r, w) as s:
                    await s.initialize()
                    return await s.call_tool("list_library", {})

        res = anyio.run(go)
        assert not res.isError
        assert json.loads(text(res)) == {"items": []}
    finally:
        proc.terminate()
        proc.wait(timeout=10)
