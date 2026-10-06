"""Library, devices and keys routes on the main app (with a valid API key)."""

import io
import zipfile

import pytest

from xteink.core import DeviceService, KeyService, LibraryService
from xteink.core.ingest import IngestEnvironmentError, IngestError

from .conftest import bearer

pytest.importorskip("fastapi")


def make_epub() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
        z.writestr("mimetype", b"application/epub+zip")
        z.writestr("META-INF/container.xml", "<container/>")
    return buf.getvalue()


@pytest.fixture
def h(api_key):
    return bearer(api_key)


def upload(client, h, data, filename, **form):
    return client.post("/api/library", files={"file": (filename, data)}, data=form, headers=h)


# --- library ---------------------------------------------------------------


def test_upload_list_get_download_delete(main_client, h, store):
    r = upload(main_client, h, b"hello world", "notes.txt", title="Notes", author="Me")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["created"] is True
    item = body["item"]
    assert (item["title"], item["author"], item["format"], item["kind"]) == (
        "Notes",
        "Me",
        "txt",
        "book",
    )

    again = upload(main_client, h, b"hello world", "notes.txt")
    assert again.status_code == 200 and again.json()["created"] is False

    listing = main_client.get("/api/library", headers=h).json()
    assert [i["id"] for i in listing["items"]] == [item["id"]]
    assert main_client.get("/api/library?kind=article", headers=h).json()["items"] == []
    assert main_client.get("/api/library?q=note", headers=h).json()["items"][0]["id"] == item["id"]
    assert main_client.get("/api/library?q=zzz", headers=h).json()["items"] == []

    meta = main_client.get(f"/api/library/{item['id']}", headers=h)
    assert meta.json() == item

    f = main_client.get(f"/api/library/{item['id']}/file", headers=h)
    assert f.status_code == 200 and f.content == b"hello world"
    assert "attachment" in f.headers["content-disposition"]
    assert "Notes.txt" in f.headers["content-disposition"]

    assert main_client.delete(f"/api/library/{item['id']}", headers=h).status_code == 204
    assert main_client.get(f"/api/library/{item['id']}", headers=h).status_code == 404
    assert main_client.get(f"/api/library/{item['id']}/file", headers=h).status_code == 404
    assert main_client.delete(f"/api/library/{item['id']}", headers=h).status_code == 404


def test_upload_epub(main_client, h):
    r = upload(main_client, h, make_epub(), "Dune.epub")
    assert r.status_code == 201
    assert r.json()["item"]["title"] == "Dune"
    f = main_client.get(f"/api/library/{r.json()['item']['id']}/file", headers=h)
    assert f.headers["content-type"] == "application/epub+zip"


def test_list_pagination_and_bad_params(main_client, h, store):
    lib = LibraryService(store)
    for n in range(3):
        lib.add(f"b{n}".encode(), title=f"B{n}", kind="book", format="txt")
    page = main_client.get("/api/library?limit=1&offset=1", headers=h).json()["items"]
    assert [i["title"] for i in page] == ["B1"]
    assert main_client.get("/api/library?kind=nope", headers=h).status_code == 422
    assert main_client.get("/api/library?limit=0", headers=h).status_code == 422


@pytest.mark.parametrize(
    "data,filename,status,code",
    [
        (b"%PDF-1.4 x", "a.pdf", 415, "pdf_not_supported"),
        (b"data", "a.docx", 415, "unsupported_format"),
        (b"not a bmp", "a.bmp", 422, "bad_magic"),
        (b"PK\x03\x04junk", "a.epub", 422, "bad_magic"),
    ],
)
def test_upload_ingest_error_mapping(main_client, h, data, filename, status, code):
    r = upload(main_client, h, data, filename)
    assert r.status_code == status, r.text
    assert r.json()["code"] == code


def test_upload_too_large_413(main_client, h, monkeypatch):
    from xteink.core.ingest import IngestLimits
    from xteink.server import routes_library

    monkeypatch.setattr(routes_library, "UPLOAD_LIMITS", IngestLimits(max_bytes=10))
    r = upload(main_client, h, b"x" * 50, "big.txt")
    assert r.status_code == 413
    assert r.json()["code"] == "too_large"


def test_upload_converter_missing_503(main_client, h, monkeypatch):
    from xteink.server import routes_library

    def boom(*a, **k):
        raise IngestEnvironmentError("pandoc is not installed")

    monkeypatch.setattr(routes_library, "ingest_and_add", boom)
    r = upload(main_client, h, b"# hi", "a.md")
    assert r.status_code == 503
    assert r.json()["code"] == "converter_missing"


def test_upload_other_ingest_error_422(main_client, h, monkeypatch):
    from xteink.server import routes_library

    def boom(*a, **k):
        raise IngestError("conversion timed out", "conversion_timeout")

    monkeypatch.setattr(routes_library, "ingest_and_add", boom)
    r = upload(main_client, h, b"# hi", "a.md")
    assert r.status_code == 422
    assert r.json()["code"] == "conversion_timeout"


def test_upload_goes_through_ingest(main_client, h, monkeypatch):
    from xteink.server import routes_library

    seen = {}
    real = routes_library.ingest_and_add

    def spy(library, data, **kw):
        seen.update(kw)
        return real(library, data, **kw)

    monkeypatch.setattr(routes_library, "ingest_and_add", spy)
    assert upload(main_client, h, b"txt", "x.txt", kind="article").status_code == 201
    assert seen["filename"] == "x.txt" and seen["kind"] == "article"


def test_upload_requires_file(main_client, h):
    assert main_client.post("/api/library", data={"title": "x"}, headers=h).status_code == 422


# --- devices ---------------------------------------------------------------


def test_device_admin_flow(main_client, h, store):
    r = main_client.post("/api/devices", json={"name": "kindle-ish", "mirror": True}, headers=h)
    assert r.status_code == 201
    dev, raw = r.json()["device"], r.json()["key"]
    assert raw.startswith("xtd_") and dev["mirror"] is True
    assert "key_hash" not in dev

    listing = main_client.get("/api/devices", headers=h).json()["devices"]
    assert [d["id"] for d in listing] == [dev["id"]]
    assert all("key" not in d for d in listing)
    assert raw not in main_client.get(f"/api/devices/{dev['id']}", headers=h).text

    m = main_client.put(f"/api/devices/{dev['id']}/mirror", json={"mirror": False}, headers=h)
    assert m.json()["mirror"] is False

    item = LibraryService(store).add(b"book", title="B", kind="book", format="txt").item
    q = main_client.post(f"/api/devices/{dev['id']}/queue", json={"item_id": item.id}, headers=h)
    assert q.status_code == 201 and q.json()["item_id"] == item.id
    queued = main_client.get(f"/api/devices/{dev['id']}/queue", headers=h).json()["entries"]
    assert [e["item_id"] for e in queued] == [item.id]
    assert (
        main_client.get(f"/api/devices/{dev['id']}/queue?state=delivered", headers=h).json()[
            "entries"
        ]
        == []
    )
    assert (
        main_client.get(f"/api/devices/{dev['id']}/queue?state=all", headers=h).json()["entries"]
        != []
    )

    rot = main_client.post(f"/api/devices/{dev['id']}/rotate", headers=h)
    new_raw = rot.json()["key"]
    assert new_raw != raw
    svc = DeviceService(store)
    assert svc.authenticate(new_raw).id == dev["id"]

    rev = main_client.post(f"/api/devices/{dev['id']}/revoke", headers=h)
    assert rev.json()["revoked_at"]


def test_device_admin_errors(main_client, h):
    assert main_client.get("/api/devices/999", headers=h).status_code == 404
    assert main_client.post("/api/devices/999/revoke", headers=h).status_code == 404
    assert main_client.post("/api/devices", json={"name": "  "}, headers=h).status_code == 422
    assert main_client.post("/api/devices", json={}, headers=h).status_code == 422
    r = main_client.post("/api/devices", json={"name": "a"}, headers=h)
    did = r.json()["device"]["id"]
    q = main_client.post(f"/api/devices/{did}/queue", json={"item_id": 42}, headers=h)
    assert q.status_code == 404
    assert main_client.get(f"/api/devices/{did}/queue?state=bogus", headers=h).status_code == 422


# --- keys ------------------------------------------------------------------


def test_keys_flow(main_client, h, store):
    r = main_client.post("/api/keys", json={"name": "laptop"}, headers=h)
    assert r.status_code == 201
    new_raw, meta = r.json()["key"], r.json()["api_key"]
    assert new_raw.startswith("xtk_") and meta["name"] == "laptop"

    listing = main_client.get("/api/keys", headers=h)
    names = [k["name"] for k in listing.json()["keys"]]
    assert names == ["test", "laptop"]
    assert new_raw not in listing.text and "key_hash" not in listing.text

    assert main_client.get("/api/keys", headers=bearer(new_raw)).status_code == 200
    assert main_client.post(f"/api/keys/{meta['id']}/revoke", headers=h).status_code == 204
    assert main_client.get("/api/keys", headers=bearer(new_raw)).status_code == 401
    assert main_client.post("/api/keys/999/revoke", headers=h).status_code == 404
    assert KeyService(store).list()[1].revoked_at


def test_keys_create_requires_name(main_client, h):
    assert main_client.post("/api/keys", json={"name": ""}, headers=h).status_code == 422
