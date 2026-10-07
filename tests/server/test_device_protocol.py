"""Device protocol v1 (docs/device-protocol.md) driven end-to-end by a fake device."""

import re
from pathlib import Path

import pytest

from xteink.core import DeviceService, LibraryService

from .conftest import bearer
from .fake_device import FakeDevice

pytest.importorskip("fastapi")

DOC = Path(__file__).resolve().parents[2] / "docs" / "device-protocol.md"
V1 = {"X-Xteink-Protocol": "1"}


@pytest.fixture
def lib(store):
    return LibraryService(store)


@pytest.fixture
def devs(store):
    return DeviceService(store)


def add(lib, data: bytes, title: str):
    return lib.add(data, title=title, kind="book", format="epub").item


def register(devs, name="reader", *, mirror=False):
    return devs.register(name, mirror=mirror)


def h(raw, **extra):
    return {**bearer(raw), **V1, **extra}


# --- criterion 1: the contract document ------------------------------------


def test_protocol_doc_specifies_v1():
    text = DOC.read_text()
    assert re.search(r"^# .*[Pp]rotocol.*v1", text, re.M)
    for needle in [
        "X-Xteink-Protocol",
        "Authorization: Bearer",
        "GET /api/device/queue",
        "GET /api/device/items/",
        "Range",
        "POST /api/device/ack",
        "POST /api/device/status",
        "free_sd_bytes",
        "firmware_version",
        "last_error",
        "sha256",
        "sd_full",
        "deletes",
        "inventory",
    ]:
        assert needle in text, needle
    for field in ["id", "title", "size", "sha256", "url"]:
        assert f'"{field}"' in text
    for code in ["401", "404", "409", "416", "422", "426"]:
        assert re.search(rf"^\| `?{code}", text, re.M), code


# --- criterion 2: full flow, resume, 426 -----------------------------------


def test_full_flow_queue_download_resume_ack_delivered(device_client, main_client, lib, devs):
    dev, raw = register(devs)
    a = add(lib, b"A" * 1000, "Alpha")
    b = add(lib, bytes(range(256)) * 7, "Beta")
    devs.queue_item(dev.id, a.id)
    devs.queue_item(dev.id, b.id)

    fake = FakeDevice(device_client, raw)
    res = fake.sync(drop_after={b.id: 300})

    assert res.delivered == [a.id, b.id]
    assert res.resumed == [b.id]
    assert {f.sha256 for f in fake.sd.values()} == {a.sha256, b.sha256}
    assert all(f.unmodified for f in fake.sd.values())
    assert devs.queue(dev.id) == []
    assert [e.item_id for e in devs.queue(dev.id, state="delivered")] == [a.id, b.id]

    # Second sync: nothing left to deliver.
    assert fake.sync().delivered == []


def test_queue_shape(device_client, lib, devs):
    dev, raw = register(devs)
    a = add(lib, b"hello", "Hello")
    devs.queue_item(dev.id, a.id)
    r = device_client.get("/api/device/queue", headers=h(raw))
    assert r.status_code == 200
    assert r.json() == {
        "protocol": "1",
        "items": [
            {
                "id": a.id,
                "title": "Hello",
                "size": 5,
                "sha256": a.sha256,
                "format": "epub",
                "url": f"/api/device/items/{a.id}",
            }
        ],
        "skipped": [],
        "deletes": [],
    }


def test_ranged_download(device_client, lib, devs):
    dev, raw = register(devs)
    data = bytes(range(100))
    a = add(lib, data, "R")
    devs.queue_item(dev.id, a.id)
    url = f"/api/device/items/{a.id}"

    full = device_client.get(url, headers=h(raw))
    assert full.status_code == 200
    assert full.content == data
    assert full.headers["accept-ranges"] == "bytes"
    assert full.headers["etag"] == f'"{a.sha256}"'

    r = device_client.get(url, headers=h(raw, Range="bytes=10-19"))
    assert r.status_code == 206
    assert r.content == data[10:20]
    assert r.headers["content-range"] == "bytes 10-19/100"
    assert r.headers["content-length"] == "10"

    r = device_client.get(url, headers=h(raw, Range="bytes=90-"))
    assert (r.status_code, r.content) == (206, data[90:])

    r = device_client.get(url, headers=h(raw, Range="bytes=-5"))
    assert (r.status_code, r.content) == (206, data[95:])

    r = device_client.get(url, headers=h(raw, Range="bytes=95-500"))
    assert (r.status_code, r.content) == (206, data[95:])
    assert r.headers["content-range"] == "bytes 95-99/100"


@pytest.mark.parametrize(
    "rng", ["bytes=100-", "bytes=50-10", "bytes=abc", "items=0-1", "bytes=0-1,5-6"]
)
def test_bad_range_416(device_client, lib, devs, rng):
    dev, raw = register(devs)
    a = add(lib, bytes(100), "R")
    devs.queue_item(dev.id, a.id)
    r = device_client.get(f"/api/device/items/{a.id}", headers=h(raw, Range=rng))
    assert r.status_code == 416
    assert r.headers["content-range"] == "bytes */100"


def test_download_only_items_for_this_device(device_client, lib, devs):
    dev, raw = register(devs, "mine")
    other, _ = register(devs, "other")
    a = add(lib, b"theirs", "T")
    devs.queue_item(other.id, a.id)
    assert device_client.get(f"/api/device/items/{a.id}", headers=h(raw)).status_code == 404
    assert device_client.get("/api/device/items/999", headers=h(raw)).status_code == 404


def test_ack_mismatch_409_and_not_queued_404(device_client, lib, devs):
    dev, raw = register(devs)
    a = add(lib, b"x", "X")
    b = add(lib, b"y", "Y")
    devs.queue_item(dev.id, a.id)
    r = device_client.post(
        "/api/device/ack", headers=h(raw), json={"item_id": a.id, "sha256": "0" * 64}
    )
    assert r.status_code == 409
    assert "sha256" in r.json()["detail"]
    assert devs.queue(dev.id)[0].state == "queued"
    r = device_client.post(
        "/api/device/ack", headers=h(raw), json={"item_id": b.id, "sha256": b.sha256}
    )
    assert r.status_code == 404
    r = device_client.post("/api/device/ack", headers=h(raw), json={"item_id": a.id})
    assert r.status_code == 422


@pytest.mark.parametrize("version", [None, "2", "0", "v1", ""])
@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/api/device/queue"),
        ("GET", "/api/device/items/1"),
        ("POST", "/api/device/ack"),
        ("POST", "/api/device/status"),
    ],
)
def test_unknown_protocol_426(device_client, devs, version, method, path):
    _, raw = register(devs)
    headers = bearer(raw)
    if version is not None:
        headers["X-Xteink-Protocol"] = version
    r = device_client.request(method, path, headers=headers, json={})
    assert r.status_code == 426
    body = r.json()["detail"]
    assert body["supported"] == ["1"]
    assert "X-Xteink-Protocol" in body["message"]
    assert r.headers["upgrade"] == "xteink-device/1"


def test_fake_device_with_future_protocol_gets_426(device_client, devs):
    _, raw = register(devs)
    fake = FakeDevice(device_client, raw, protocol="2")
    assert fake.get_queue().status_code == 426


# --- criterion 3: sd_full, mirror deletes, revoked key ---------------------


def test_sd_full_omits_oversized_items(device_client, lib, devs):
    from xteink.server.routes_device import SD_SAFETY_MARGIN

    dev, raw = register(devs)
    small = add(lib, b"s" * 1000, "Small")
    big = add(lib, b"b" * 50_000, "Big")
    small2 = add(lib, b"t" * 2000, "Small2")
    for it in (small, big, small2):
        devs.queue_item(dev.id, it.id)

    fake = FakeDevice(device_client, raw, sd_capacity=SD_SAFETY_MARGIN + 10_000)
    res = fake.sync()
    assert res.delivered == [small.id, small2.id]
    assert res.skipped == [{"id": big.id, "reason": "sd_full"}]
    assert [e.item_id for e in devs.queue(dev.id)] == [big.id]


def test_sd_full_is_cumulative(device_client, lib, devs):
    from xteink.server.routes_device import SD_SAFETY_MARGIN

    dev, raw = register(devs)
    a = add(lib, b"a" * 600, "A")
    b = add(lib, b"b" * 600, "B")
    devs.queue_item(dev.id, a.id)
    devs.queue_item(dev.id, b.id)
    devs.report_status(dev.id, free_sd_bytes=SD_SAFETY_MARGIN + 1000)
    q = device_client.get("/api/device/queue", headers=h(raw)).json()
    assert [i["id"] for i in q["items"]] == [a.id]
    assert q["skipped"] == [{"id": b.id, "reason": "sd_full"}]


def test_unknown_free_space_does_not_filter(device_client, lib, devs):
    dev, raw = register(devs)
    a = add(lib, b"a" * 600, "A")
    devs.queue_item(dev.id, a.id)
    q = device_client.get("/api/device/queue", headers=h(raw)).json()
    assert [i["id"] for i in q["items"]] == [a.id]
    assert q["skipped"] == []


def _deliver_two_then_delete(device_client, lib, devs, *, mirror):
    dev, raw = register(devs, mirror=mirror)
    keep = add(lib, b"keep" * 100, "Keep")
    gone = add(lib, b"gone" * 100, "Gone")
    edited = add(lib, b"edit" * 100, "Edited")
    for it in (keep, gone, edited):
        devs.queue_item(dev.id, it.id)
    fake = FakeDevice(device_client, raw)
    assert fake.sync().delivered == [keep.id, gone.id, edited.id]
    fake.sideload("mine.epub", b"user file")
    # User annotates "Edited" on-device, then both are removed from the library.
    name = next(n for n, f in fake.sd.items() if f.sha256 == edited.sha256)
    fake.sd[name].data += b"<note/>"
    lib.delete(gone.id)
    lib.delete(edited.id)
    return dev, raw, fake, keep, gone, edited


def test_mirror_deletes_only_unmodified_delivered(device_client, lib, devs):
    dev, raw, fake, keep, gone, edited = _deliver_two_then_delete(
        device_client, lib, devs, mirror=True
    )
    fake.post_status().raise_for_status()
    q = device_client.get("/api/device/queue", headers=h(raw)).json()
    assert q["deletes"] == [{"sha256": gone.sha256}]

    res = fake.sync()
    assert res.deleted == [gone.sha256]
    shas = {f.sha256 for f in fake.sd.values()}
    assert shas == {keep.sha256, edited.sha256, None}  # sideloaded file untouched
    assert "mine.epub" in fake.sd
    # Once removed and reported, no further delete instructions.
    fake.post_status().raise_for_status()
    assert device_client.get("/api/device/queue", headers=h(raw)).json()["deletes"] == []


def test_non_mirror_device_never_gets_deletes(device_client, lib, devs):
    dev, raw, fake, keep, gone, edited = _deliver_two_then_delete(
        device_client, lib, devs, mirror=False
    )
    res = fake.sync()
    assert res.deleted == []
    assert {f.sha256 for f in fake.sd.values()} == {keep.sha256, gone.sha256, edited.sha256, None}


def test_inventory_is_per_device(device_client, lib, devs):
    d1, raw1 = register(devs, "one", mirror=True)
    d2, raw2 = register(devs, "two", mirror=True)
    gone = add(lib, b"bye", "Bye")
    lib.delete(gone.id)
    device_client.post(
        "/api/device/status",
        headers=h(raw1),
        json={"free_sd_bytes": 10**6, "inventory": [{"sha256": gone.sha256, "unmodified": True}]},
    ).raise_for_status()
    assert device_client.get("/api/device/queue", headers=h(raw2)).json()["deletes"] == []
    q1 = device_client.get("/api/device/queue", headers=h(raw1)).json()
    assert q1["deletes"] == [{"sha256": gone.sha256}]


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/api/device/queue"),
        ("GET", "/api/device/items/1"),
        ("POST", "/api/device/ack"),
        ("POST", "/api/device/status"),
    ],
)
def test_revoked_key_401(device_client, devs, method, path):
    dev, raw = register(devs)
    devs.revoke_key(dev.id)
    r = device_client.request(method, path, headers=h(raw), json={})
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"


def test_revoked_key_401_even_with_bad_protocol(device_client, devs):
    dev, raw = register(devs)
    devs.revoke_key(dev.id)
    r = device_client.get("/api/device/queue", headers={**bearer(raw), "X-Xteink-Protocol": "9"})
    assert r.status_code == 401


def test_fake_device_revoked_mid_life(device_client, lib, devs):
    dev, raw = register(devs)
    fake = FakeDevice(device_client, raw)
    assert fake.get_queue().status_code == 200
    devs.revoke_key(dev.id)
    assert fake.get_queue().status_code == 401


# --- criterion 4: status readable via /api/devices/{id} --------------------


def test_device_status_via_admin_api(device_client, main_client, api_key, lib, devs):
    dev, raw = register(devs)
    a = add(lib, b"a" * 10, "A")
    b = add(lib, b"b" * 10, "B")
    devs.queue_item(dev.id, a.id)
    devs.queue_item(dev.id, b.id)
    fake = FakeDevice(device_client, raw, firmware_version="fw-9")
    fake.post_status().raise_for_status()
    fake.download({**device_client.get("/api/device/queue", headers=h(raw)).json()["items"][0]})
    fake.ack(a.id, a.sha256).raise_for_status()
    fake.last_sync_result = "partial"
    fake.last_error = "wifi dropped"
    fake.post_status().raise_for_status()

    r = main_client.get(f"/api/devices/{dev.id}", headers=bearer(api_key))
    assert r.status_code == 200
    s = r.json()
    assert s["last_seen"]
    assert s["last_sync_result"] == "partial"
    assert s["last_error"] == "wifi dropped"
    assert s["firmware_version"] == "fw-9"
    assert s["free_sd_bytes"] == fake.free_sd_bytes

    r = main_client.get(f"/api/devices/{dev.id}/queue?state=all", headers=bearer(api_key))
    states = {e["item_id"]: e["state"] for e in r.json()["entries"]}
    assert states == {a.id: "delivered", b.id: "queued"}


def test_status_validates_body(device_client, devs):
    _, raw = register(devs)
    r = device_client.post("/api/device/status", headers=h(raw), json={"free_sd_bytes": -1})
    assert r.status_code == 422
    r = device_client.post(
        "/api/device/status", headers=h(raw), json={"inventory": [{"sha256": "nothex"}]}
    )
    assert r.status_code == 422


def test_status_response_and_hash_helper(device_client, devs):
    dev, raw = register(devs)
    r = device_client.post(
        "/api/device/status",
        headers=h(raw),
        json={"free_sd_bytes": 5, "firmware_version": "f", "last_sync_result": "ok"},
    )
    assert r.status_code == 200
    assert r.json()["protocol"] == "1"
    assert r.json()["device"]["id"] == dev.id
    assert "key_id" not in r.json()["device"]
