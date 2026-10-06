import hashlib
import sqlite3

import pytest

from xteink.core import AuthError, NotFoundError, ValidationError


def _item(library, data=b"book"):
    return library.add(data, title="T", kind="book", format="epub").item


def test_register_returns_key_once_and_stores_hash(devices, store):
    dev, raw = devices.register("reader", mirror=True)
    assert dev.name == "reader" and dev.mirror is True and dev.revoked_at is None
    assert raw.startswith("xtd_") and dev.key_id in raw
    row = sqlite3.connect(store.db_path).execute("select * from devices").fetchone()
    assert raw not in repr(row)
    assert hashlib.sha256(raw.encode()).hexdigest() in repr(row)


def test_authenticate_and_last_seen(devices):
    dev, raw = devices.register("r")
    assert dev.last_seen is None
    got = devices.authenticate(raw)
    assert got.id == dev.id and got.last_seen is not None


def test_authenticate_rejects_bad_keys(devices):
    dev, raw = devices.register("r")
    for bad in ("", "garbage", raw + "x", raw[:-1] + ("a" if raw[-1] != "a" else "b")):
        with pytest.raises(AuthError):
            devices.authenticate(bad)


def test_revoke_key(devices):
    dev, raw = devices.register("r")
    devices.revoke_key(dev.id)
    with pytest.raises(AuthError):
        devices.authenticate(raw)
    assert devices.get(dev.id).revoked_at is not None
    with pytest.raises(NotFoundError):
        devices.revoke_key(999)


def test_rotate_key(devices):
    dev, old = devices.register("r")
    new = devices.rotate_key(dev.id)
    with pytest.raises(AuthError):
        devices.authenticate(old)
    assert devices.authenticate(new).id == dev.id


def test_queue_and_deliver(devices, library):
    dev, _ = devices.register("r")
    item = _item(library)
    entry = devices.queue_item(dev.id, item.id)
    assert entry.state == "queued"
    assert devices.queue_item(dev.id, item.id).id == entry.id  # idempotent
    q = devices.queue(dev.id)
    assert [(e.item_id, e.sha256, e.size, e.title) for e in q] == [
        (item.id, item.sha256, item.size, "T")
    ]
    done = devices.mark_delivered(dev.id, item.id, item.sha256)
    assert done.state == "delivered" and done.delivered_at is not None
    assert devices.queue(dev.id) == []
    assert len(devices.queue(dev.id, state="delivered")) == 1


def test_mark_delivered_wrong_sha(devices, library):
    dev, _ = devices.register("r")
    item = _item(library)
    devices.queue_item(dev.id, item.id)
    with pytest.raises(ValidationError):
        devices.mark_delivered(dev.id, item.id, "0" * 64)
    assert len(devices.queue(dev.id)) == 1
    with pytest.raises(NotFoundError):
        devices.mark_delivered(dev.id, 999, item.sha256)


def test_queue_unknown_refs(devices, library):
    dev, _ = devices.register("r")
    with pytest.raises(NotFoundError):
        devices.queue_item(dev.id, 42)
    with pytest.raises(NotFoundError):
        devices.queue_item(999, _item(library).id)


def test_status_report(devices):
    dev, _ = devices.register("r")
    devices.report_status(
        dev.id,
        last_sync_result="ok",
        free_sd_bytes=1234,
        firmware_version="0.1.0",
        last_error=None,
    )
    s = devices.status(dev.id)
    assert (s.last_sync_result, s.free_sd_bytes, s.firmware_version) == ("ok", 1234, "0.1.0")
    assert s.last_seen is not None
    assert [d.id for d in devices.list()] == [dev.id]


def test_deleting_item_drops_queue_entries(devices, library):
    dev, _ = devices.register("r")
    item = _item(library)
    devices.queue_item(dev.id, item.id)
    library.delete(item.id)
    assert devices.queue(dev.id, state=None) == []


def test_api_keys(keys):
    rec, raw = keys.create("agent")
    assert raw.startswith("xtk_")
    assert keys.authenticate(raw).id == rec.id
    keys.revoke(rec.id)
    with pytest.raises(AuthError):
        keys.authenticate(raw)
    with pytest.raises(AuthError):
        keys.authenticate("xtk_nope_nope")
    assert len(keys.list()) == 1
