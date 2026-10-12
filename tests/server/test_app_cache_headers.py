"""index.html must revalidate on every load; hashed assets may be cached forever."""

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from xteink.core.store import Store  # noqa: E402
from xteink.server.app import create_app  # noqa: E402


@pytest.fixture
def client(tmp_path):
    web = tmp_path / "web"
    (web / "assets").mkdir(parents=True)
    (web / "index.html").write_text("<!doctype html><title>xteink library</title>")
    (web / "assets" / "index-AbC123.js").write_text("console.log(1)")
    return TestClient(create_app(Store(tmp_path / "data"), webassets_dir=web))


def test_index_is_no_cache(client):
    for path in ("/", "/index.html"):
        r = client.get(path)
        assert r.status_code == 200
        assert r.headers["cache-control"] == "no-cache"


def test_hashed_assets_are_immutable(client):
    r = client.get("/assets/index-AbC123.js")
    assert r.status_code == 200
    assert "immutable" in r.headers["cache-control"]
