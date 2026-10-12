"""``/api/firmware`` on the main app: validated upload, dry-run, list, offer."""

from pathlib import Path

import pytest

from xteink.core import DeviceService, FirmwareStore

from .conftest import bearer

pytest.importorskip("fastapi")

VALID = (Path(__file__).resolve().parents[1] / "fixtures" / "fw" / "valid_x3.bin").read_bytes()


@pytest.fixture
def h(api_key):
    return bearer(api_key)


def upload(client, h, data=VALID, **form):
    form.setdefault("fork_commit", "abc123")
    form.setdefault("source_pr", "https://example.test/pr/1")
    return client.post("/api/firmware", files={"file": ("fw.bin", data)}, data=form, headers=h)


def test_requires_operator(main_client):
    assert main_client.get("/api/firmware").status_code == 401
    assert main_client.post("/api/firmware/1/offer", json={"all": True}).status_code == 401
    assert main_client.post("/api/firmware", files={"file": ("a", VALID)}).status_code == 401


def test_upload_list_get(main_client, h):
    r = upload(main_client, h)
    assert r.status_code == 201
    body = r.json()
    fw = body["firmware"]
    assert body["created"] is True
    assert fw["version"] == "1.6.5-dev"
    assert fw["board"] == "x4"
    assert fw["size"] == len(VALID)
    assert fw["fork_commit"] == "abc123"
    assert fw["source_pr"] == "https://example.test/pr/1"
    assert main_client.get("/api/firmware", headers=h).json()["firmware"] == [fw]
    assert main_client.get(f"/api/firmware/{fw['id']}", headers=h).json() == fw
    assert main_client.get("/api/firmware/99", headers=h).status_code == 404
    again = upload(main_client, h)
    assert again.status_code == 200
    assert again.json()["created"] is False


def test_dry_run_stores_nothing(main_client, h, store):
    r = upload(main_client, h, dry_run="true")
    assert r.status_code == 200
    assert r.json()["dry_run"] is True
    assert r.json()["image"]["version"] == "1.6.5-dev"
    assert FirmwareStore(store).list() == []


@pytest.mark.parametrize(
    "data,code",
    [
        (b"", "truncated"),
        (b"\x00" * 64, "bad_magic"),
        (b"\xe9" + b"\x00" * 11 + b"\x09\x00" + b"\x00" * 50, "wrong_chip"),
        (VALID.replace(b"CROSSPOINT-BOARD-V1:x4;", b"CROSSPOINT-BOARD-V1:x5;"), "wrong_board"),
    ],
)
def test_bad_image_422_and_nothing_stored(main_client, h, store, data, code):
    r = upload(main_client, h, data=data)
    assert r.status_code == 422
    assert r.json()["code"] == code
    assert FirmwareStore(store).list() == []


def test_too_large_413(main_client, h, store, monkeypatch):
    monkeypatch.setattr("xteink.server.routes_admin.MAX_IMAGE_SIZE", 10)
    monkeypatch.setattr("xteink.core.fwimage.MAX_IMAGE_SIZE", 10)
    r = upload(main_client, h)
    assert r.status_code == 413
    assert r.json()["code"] == "too_large"
    assert FirmwareStore(store).list() == []


def test_version_required_when_image_has_none(main_client, h, store):
    bare = VALID.replace(b"CrossPoint version: ", b"CrossPoint vers!on: ")
    r = upload(main_client, h, data=bare)
    assert r.status_code == 422
    assert r.json()["code"] == "version_required"
    assert FirmwareStore(store).list() == []
    ok = upload(main_client, h, data=bare, version="9.9.9")
    assert ok.status_code == 201
    assert ok.json()["firmware"]["version"] == "9.9.9"


def test_offer_single_and_dry_run(main_client, h, store):
    dev = DeviceService(store).register("reader")[0]
    fid = upload(main_client, h).json()["firmware"]["id"]
    url = f"/api/firmware/{fid}/offer"
    dry = main_client.post(url, json={"device_id": dev.id, "dry_run": True}, headers=h)
    assert dry.status_code == 200
    assert dry.json()["offered"] == [dev.id]
    assert FirmwareStore(store).offered(dev.id) is None
    r = main_client.post(url, json={"device_id": dev.id}, headers=h)
    assert r.status_code == 200
    assert r.json()["dry_run"] is False
    assert FirmwareStore(store).offered(dev.id).id == fid
    listed = main_client.get("/api/devices", headers=h).json()["devices"][0]
    assert listed["offered_firmware_id"] == fid


def test_offer_refusals(main_client, h, store):
    devs = DeviceService(store)
    revoked = devs.register("gone")[0]
    devs.revoke_key(revoked.id)
    rolled = devs.register("rolled")[0]
    fid = upload(main_client, h).json()["firmware"]["id"]
    FirmwareStore(store).record_rollback(rolled.id, fid)
    url = f"/api/firmware/{fid}/offer"
    for dev in (revoked, rolled):
        for dry in (True, False):
            r = main_client.post(url, json={"device_id": dev.id, "dry_run": dry}, headers=h)
            assert r.status_code == 422, (dev.name, dry)
    assert main_client.post(url, json={"device_id": 999}, headers=h).status_code == 404
    assert (
        main_client.post("/api/firmware/99/offer", json={"all": True}, headers=h).status_code == 404
    )
    assert main_client.post(url, json={}, headers=h).status_code == 422
    assert main_client.post(url, json={"all": True, "device_id": 1}, headers=h).status_code == 422


def test_offer_all(main_client, h, store):
    devs = DeviceService(store)
    ok = devs.register("ok")[0]
    revoked = devs.register("gone")[0]
    devs.revoke_key(revoked.id)
    rolled = devs.register("rolled")[0]
    fid = upload(main_client, h).json()["firmware"]["id"]
    FirmwareStore(store).record_rollback(rolled.id, fid)
    url = f"/api/firmware/{fid}/offer"
    dry = main_client.post(url, json={"all": True, "dry_run": True}, headers=h).json()
    assert dry["offered"] == [ok.id]
    assert FirmwareStore(store).offered(ok.id) is None
    res = main_client.post(url, json={"all": True}, headers=h).json()
    assert res["offered"] == [ok.id]
    assert res["skipped_revoked"] == [revoked.id]
    assert res["skipped_rolled_back"] == [rolled.id]
    assert FirmwareStore(store).offered(ok.id).id == fid


def test_rollbacks_route(main_client, h, store):
    rolled = DeviceService(store).register("rolled")[0]
    fid = upload(main_client, h).json()["firmware"]["id"]
    url = f"/api/firmware/{fid}/rollbacks"
    assert main_client.get(url).status_code == 401
    assert main_client.get(url, headers=h).json() == {"rollbacks": []}
    FirmwareStore(store).record_rollback(rolled.id, fid)
    (row,) = main_client.get(url, headers=h).json()["rollbacks"]
    assert row["device_id"] == rolled.id
    assert row["device_name"] == "rolled"
    assert row["rolled_back_at"]
    assert main_client.get("/api/firmware/99/rollbacks", headers=h).status_code == 404
