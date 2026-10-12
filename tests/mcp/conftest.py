"""Live-API fixtures: the real FastAPI app on an ephemeral port, in a background thread."""

import os
import socket
import stat
import sys
import threading
import time

import pytest

from xteink.core import DeviceService, KeyService, Store

pytest.importorskip("fastapi")
pytest.importorskip("uvicorn")
pytest.importorskip("mcp")

# Fake pandoc (as in tests/core/test_ingest.py): writes a minimal EPUB so Markdown ingest works
# without pandoc installed. It runs inside the API process (thread), found via PATH.
FAKE_PANDOC = """
import sys, zipfile
a = sys.argv
out = a[a.index("-o") + 1]
with zipfile.ZipFile(out, "w") as z:
    z.writestr("mimetype", "application/epub+zip")
"""


@pytest.fixture
def fake_pandoc(tmp_path, monkeypatch):
    d = tmp_path / "bin"
    d.mkdir()
    p = d / "pandoc"
    p.write_text(f"#!{sys.executable}\n" + FAKE_PANDOC)
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{d}{os.pathsep}{os.environ.get('PATH', '')}")
    return d


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "data")


@pytest.fixture
def api_key(store):
    return KeyService(store).create("mcp-test")[1]


@pytest.fixture
def device(store):
    return DeviceService(store).register("reader")[0]


@pytest.fixture
def api_url(store, fake_pandoc):
    import uvicorn

    from xteink.server.app import create_app

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(create_app(store), host="127.0.0.1", port=port, log_level="warning")
    )
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    deadline = time.time() + 10
    while not server.started and time.time() < deadline:
        time.sleep(0.02)
    assert server.started, "test API did not start"
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    t.join(timeout=10)
