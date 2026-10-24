"""Device protocol v1 (docs/device-protocol.md) driven end-to-end by a fake device."""

import hashlib
import re
from pathlib import Path

import pytest

from xteink.core import DeviceService, FirmwareStore, LibraryService, ValidationError

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
                "kind": "book",
                "url": f"/api/device/items/{a.id}",
            }
        ],
        "skipped": [],
        "deletes": [],
    }


@pytest.mark.parametrize("kind", ["article", "transcript", "newspaper"])
def test_queue_entries_carry_kind(device_client, lib, devs, kind):
    dev, raw = register(devs)
    a = lib.add(kind.encode(), title="K", kind=kind, format="epub").item
    devs.queue_item(dev.id, a.id)
    r = device_client.get("/api/device/queue", headers=h(raw))
    assert r.json()["protocol"] == "1"
    assert [i["kind"] for i in r.json()["items"]] == [kind]


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
        ("GET", "/api/device/firmware/1"),
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
        ("GET", "/api/device/firmware/1"),
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


# --- OTA + daily run: additive v1 fields and routes -------------------------

FW_V1 = "xteink-fw 0.1.0"  # FakeDevice's default firmware_version
IMAGE = bytes(range(256)) * 40  # 10 KiB stand-in image (the store does not parse it)


@pytest.fixture
def fws(store):
    return FirmwareStore(store)


def add_fw(fws, version="xteink-fw 0.2.0", data=IMAGE):
    return fws.add(data, version=version, board="x3").firmware


def status(client, raw, **body):
    return client.post("/api/device/status", headers=h(raw), json=body)


def test_protocol_doc_specifies_additive_v1_ota_fields():
    text = DOC.read_text()
    for needle in [
        "GET /api/device/firmware/",
        '"firmware"',
        "run_started_at",
        "run_trigger",
        "power_on",
        "wake",
        "manual",
        "fw_outcome",
        "installed",
        "failed:",
        "deferred:",
        "content_outcome",
        "rolled_back_version",
        "additive",
    ]:
        assert needle in text, needle


def test_old_client_syncs_unchanged_with_an_offer_pending(device_client, lib, devs, fws):
    dev, raw = register(devs)
    a = add(lib, b"A" * 500, "Alpha")
    devs.queue_item(dev.id, a.id)
    fws.offer(dev.id, add_fw(fws).id)

    fake = FakeDevice(device_client, raw)  # old client: default mode
    assert set(fake.status_body()) == {
        "free_sd_bytes",
        "firmware_version",
        "last_error",
        "last_sync_result",
        "inventory",
    }
    r = fake.post_status()
    assert r.status_code == 200
    assert r.json()["protocol"] == "1"
    assert fake.get_queue().status_code == 200
    res = fake.sync(drop_after={a.id: 100})
    assert (res.delivered, res.resumed, res.firmware_offer) == ([a.id], [a.id], None)
    assert fake.firmware_image is None
    d = devs.get(dev.id)
    assert (d.last_run_at, d.last_run_trigger, d.last_fw_outcome, d.last_content_outcome) == (
        None,
        None,
        None,
        None,
    )
    assert fws.rolled_back(dev.id) == []


def test_new_client_receives_offer_and_downloads_with_resume(device_client, lib, devs, fws):
    dev, raw = register(devs)
    fw = add_fw(fws)
    fws.offer(dev.id, fw.id)
    fake = FakeDevice(device_client, raw, new_client=True)
    fake.run_started_at, fake.run_trigger = "2026-10-11T06:00:00Z", "power_on"

    res = fake.sync(firmware_drop_after=3000)
    assert res.firmware_offer == {
        "id": fw.id,
        "version": "xteink-fw 0.2.0",
        "size": len(IMAGE),
        "sha256": fw.sha256,
        "url": f"/api/device/firmware/{fw.id}",
    }
    assert res.firmware_resumed is True
    assert fake.firmware_image == IMAGE
    assert hashlib.sha256(fake.firmware_image).hexdigest() == fw.sha256

    # After installing, the device reports the new version: the offer is no longer sent.
    fake.firmware_version, fake.fw_outcome = "xteink-fw 0.2.0", "installed"
    r = fake.post_status()
    assert r.status_code == 200
    assert "firmware" not in r.json()
    d = devs.get(dev.id)
    assert (d.last_fw_outcome, d.last_run_trigger) == ("installed", "power_on")


def test_no_offer_when_versions_match_or_nothing_offered(device_client, devs, fws):
    dev, raw = register(devs)
    assert "firmware" not in status(device_client, raw, firmware_version=FW_V1).json()
    fws.offer(dev.id, add_fw(fws, version=FW_V1).id)
    assert "firmware" not in status(device_client, raw, firmware_version=FW_V1).json()
    # Version omitted: the stored firmware_version decides.
    assert "firmware" not in status(device_client, raw).json()
    fws.offer(dev.id, add_fw(fws, version="9", data=b"other").id)
    assert status(device_client, raw).json()["firmware"]["version"] == "9"


def test_offer_is_withdrawn_once_the_device_runs_it(device_client, devs, fws):
    """A fulfilled offer must not come back as a downgrade when the device later runs
    another build (a USB flash, or an image that arrived another way)."""
    dev, raw = register(devs)
    fw = add_fw(fws, version=FW_V1)
    fws.offer(dev.id, fw.id)
    assert status(device_client, raw, firmware_version="xteink-fw 0.0.9").json()["firmware"]
    assert fws.offered(dev.id).id == fw.id  # not running it yet: the offer stays

    assert "firmware" not in status(device_client, raw, firmware_version=FW_V1).json()
    assert fws.offered(dev.id) is None  # running it: the offer is fulfilled

    later = status(device_client, raw, firmware_version="xteink-fw 0.3.0-dev").json()
    assert "firmware" not in later  # no silent downgrade back to FW_V1
    assert fws.offered(dev.id) is None


def test_withdrawing_a_fulfilled_offer_keeps_a_newer_offer(device_client, devs, fws):
    dev, raw = register(devs)
    old = add_fw(fws, version=FW_V1)
    new = add_fw(fws, version="xteink-fw 0.4.0", data=b"newer image")
    fws.offer(dev.id, new.id)
    # Still running the old build: the newer offer is not the one being run, so it stays.
    assert status(device_client, raw, firmware_version=old.version).json()["firmware"]["id"] == (
        new.id
    )
    assert fws.offered(dev.id).id == new.id


def test_firmware_route_ranges_etag_and_416(device_client, devs, fws):
    dev, raw = register(devs)
    fw = add_fw(fws)
    fws.offer(dev.id, fw.id)
    url = f"/api/device/firmware/{fw.id}"
    full = device_client.get(url, headers=h(raw))
    assert full.status_code == 200
    assert full.content == IMAGE
    assert full.headers["etag"] == f'"{fw.sha256}"'
    assert full.headers["accept-ranges"] == "bytes"
    assert full.headers["content-type"] == "application/octet-stream"
    r = device_client.get(url, headers=h(raw, Range="bytes=10-19"))
    assert (r.status_code, r.content) == (206, IMAGE[10:20])
    assert r.headers["content-range"] == f"bytes 10-19/{len(IMAGE)}"
    r = device_client.get(url, headers=h(raw, Range=f"bytes={len(IMAGE)}-"))
    assert r.status_code == 416
    assert r.headers["content-range"] == f"bytes */{len(IMAGE)}"


def test_firmware_route_serves_only_own_offer(device_client, devs, fws):
    dev, raw = register(devs, "mine")
    other, _ = register(devs, "other")
    mine = add_fw(fws)
    theirs = add_fw(fws, version="x", data=b"theirs")
    fws.offer(other.id, theirs.id)
    # Nothing offered to this device yet: even an existing image is 404.
    assert device_client.get(f"/api/device/firmware/{mine.id}", headers=h(raw)).status_code == 404
    fws.offer(dev.id, mine.id)
    for fid in (theirs.id, 999):
        r = device_client.get(f"/api/device/firmware/{fid}", headers=h(raw))
        assert r.status_code == 404
    assert device_client.get(f"/api/device/firmware/{mine.id}", headers=h(raw)).status_code == 200


@pytest.mark.parametrize(
    "outcome", ["none", "installed", "failed:E42", "failed:sha256", "deferred:low_battery"]
)
def test_fw_outcome_round_trips(device_client, main_client, api_key, devs, outcome):
    dev, raw = register(devs)
    r = status(device_client, raw, fw_outcome=outcome)
    assert r.status_code == 200
    assert r.json()["device"]["last_fw_outcome"] == outcome
    assert devs.get(dev.id).last_fw_outcome == outcome
    s = main_client.get(f"/api/devices/{dev.id}", headers=bearer(api_key)).json()
    assert s["last_fw_outcome"] == outcome


@pytest.mark.parametrize("trigger", ["power_on", "wake", "manual"])
def test_run_fields_round_trip(device_client, devs, trigger):
    dev, raw = register(devs)
    r = status(
        device_client,
        raw,
        run_started_at="2026-10-11T06:00:03Z",
        run_trigger=trigger,
        content_outcome="ok",
    )
    assert r.status_code == 200
    d = devs.get(dev.id)
    assert (d.last_run_at, d.last_run_trigger, d.last_content_outcome) == (
        "2026-10-11T06:00:03Z",
        trigger,
        "ok",
    )


@pytest.mark.parametrize(
    "body",
    [
        {"fw_outcome": "bogus"},
        {"fw_outcome": "failed:"},
        {"fw_outcome": "deferred:"},
        {"fw_outcome": "installed:yes"},
        {"fw_outcome": "failed:" + "x" * 300},
        {"run_trigger": "cron"},
        {"run_started_at": "x" * 300},
        {"content_outcome": "x" * 300},
        {"rolled_back_version": "x" * 300},
    ],
)
def test_new_status_fields_validated(device_client, devs, body):
    _, raw = register(devs)
    assert status(device_client, raw, **body).status_code == 422


def test_rolled_back_version_records_rollback_and_stops_offer(device_client, devs, fws):
    dev, raw = register(devs)
    fw = add_fw(fws)
    fws.offer(dev.id, fw.id)
    fake = FakeDevice(device_client, raw, new_client=True)
    assert fake.sync().firmware_offer["id"] == fw.id

    fake.rolled_back_version, fake.fw_outcome = "xteink-fw 0.2.0", "failed:boot"
    r = fake.post_status()
    assert r.status_code == 200
    assert "firmware" not in r.json()
    assert [f.id for f in fws.rolled_back(dev.id)] == [fw.id]
    assert fws.offered(dev.id) is None
    assert devs.get(dev.id).last_fw_outcome == "failed:boot"
    with pytest.raises(ValidationError):
        fws.offer(dev.id, fw.id)
    assert dev.id in fws.offer_all(fw.id).skipped_rolled_back
    assert fake.sync().firmware_offer is None
    r = device_client.get(f"/api/device/firmware/{fw.id}", headers=h(raw))
    assert r.status_code == 404


def test_unknown_rolled_back_version_is_ignored(device_client, devs, fws):
    dev, raw = register(devs)
    fw = add_fw(fws)
    fws.offer(dev.id, fw.id)
    r = status(device_client, raw, rolled_back_version="never-uploaded")
    assert r.status_code == 200
    assert r.json()["firmware"]["id"] == fw.id
    assert fws.rolled_back(dev.id) == []


def test_rolled_back_version_prefers_offered_then_newest(device_client, devs, fws):
    dev, raw = register(devs)
    old = add_fw(fws, version="dup", data=b"one")
    new = add_fw(fws, version="dup", data=b"two")
    fws.offer(dev.id, old.id)
    status(device_client, raw, rolled_back_version="dup").raise_for_status()
    assert [f.id for f in fws.rolled_back(dev.id)] == [old.id]

    other, raw2 = register(devs, "other")
    status(device_client, raw2, rolled_back_version="dup").raise_for_status()
    assert [f.id for f in fws.rolled_back(other.id)] == [new.id]


def test_real_version_formats_match_without_the_device_prefix(device_client, devs, fws):
    """An uploaded image stores the bare version read from the image; the device reports
    it with the ``xteink-fw `` prefix. They must compare as the same build."""
    dev, raw = register(devs)
    fw = add_fw(fws, version="1.6.5+xteink.f96ca3c6", data=b"release")
    fws.offer(dev.id, fw.id)
    old = status(device_client, raw, firmware_version="xteink-fw 1.6.5+xteink.0badc0de")
    assert old.json()["firmware"]["version"] == "1.6.5+xteink.f96ca3c6"
    installed = status(device_client, raw, firmware_version="xteink-fw 1.6.5+xteink.f96ca3c6")
    assert "firmware" not in installed.json()


def test_prefixed_rolled_back_version_finds_the_bare_upload(device_client, devs, fws):
    dev, raw = register(devs)
    fw = add_fw(fws, version="1.6.5+xteink.f96ca3c6", data=b"release")
    fws.offer(dev.id, fw.id)
    r = status(device_client, raw, rolled_back_version="xteink-fw 1.6.5+xteink.f96ca3c6")
    assert r.status_code == 200
    assert "firmware" not in r.json()
    assert [f.id for f in fws.rolled_back(dev.id)] == [fw.id]
    assert fws.offered(dev.id) is None
