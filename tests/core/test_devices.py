import hashlib
import sqlite3

import pytest

from xteink.core import AuthError, NotFoundError, ValidationError


def _item(library, data=b"book"):
    return library.add(data, title="T", kind="book", format="epub").item


def test_register_returns_key_once_and_stores_hash(devices, store):
    dev, raw = devices.register("reader", mirror=True)
    assert dev.name == "reader"
    assert dev.mirror is True
    assert dev.revoked_at is None
    assert raw.startswith("xtd_")
    assert dev.key_id in raw
    row = sqlite3.connect(store.db_path).execute("select * from devices").fetchone()
    assert raw not in repr(row)
    assert hashlib.sha256(raw.encode()).hexdigest() in repr(row)


def test_authenticate_and_last_seen(devices):
    dev, raw = devices.register("r")
    assert dev.last_seen is None
    got = devices.authenticate(raw)
    assert got.id == dev.id
    assert got.last_seen is not None


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
    assert done.state == "delivered"
    assert done.delivered_at is not None
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
    item_id = _item(library).id
    with pytest.raises(NotFoundError):
        devices.queue_item(999, item_id)


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


def test_requeueing_a_delivered_item_queues_it_again(devices, library):
    dev, _ = devices.register("r")
    item = _item(library)
    devices.queue_item(dev.id, item.id)
    devices.mark_delivered(dev.id, item.id, item.sha256)
    again = devices.queue_item(dev.id, item.id)
    assert again.state == "queued"
    assert again.delivered_at is None
    assert [e.item_id for e in devices.queue(dev.id)] == [item.id]


def test_status_report_keeps_device_facts_it_leaves_out(devices):
    dev, _ = devices.register("r")
    devices.report_status(dev.id, free_sd_bytes=1000, firmware_version="1.2")
    after = devices.report_status(dev.id, last_sync_result="ok")
    assert after.free_sd_bytes == 1000
    assert after.firmware_version == "1.2"
    assert after.last_sync_result == "ok"


def test_queue_entries_carry_the_item_format(devices, library):
    dev, _ = devices.register("r")
    item = _item(library)
    entry = devices.queue_item(dev.id, item.id)
    assert entry.format == "epub"


def test_report_status_records_daily_run_fields(devices):
    dev, _ = devices.register("r")
    s = devices.report_status(
        dev.id,
        run_started_at="2026-10-11T06:00:00Z",
        run_trigger="wake",
        fw_outcome="deferred:low_battery",
        content_outcome="ok",
    )
    assert (s.last_run_at, s.last_run_trigger) == ("2026-10-11T06:00:00Z", "wake")
    assert (s.last_fw_outcome, s.last_content_outcome) == ("deferred:low_battery", "ok")


def test_report_status_keeps_run_fields_when_omitted(devices):
    dev, _ = devices.register("r")
    devices.report_status(
        dev.id, run_started_at="t0", run_trigger="power_on", fw_outcome="installed"
    )
    after = devices.report_status(dev.id, last_sync_result="ok", content_outcome="partial")
    assert (after.last_run_at, after.last_run_trigger) == ("t0", "power_on")
    assert (after.last_fw_outcome, after.last_content_outcome) == ("installed", "partial")


def test_queue_entries_carry_the_item_kind(devices, library):
    dev, _ = devices.register("k")
    for i, kind in enumerate(("book", "article", "transcript", "newspaper")):
        item = library.add(b"kind%d" % i, title="T", kind=kind, format="epub").item
        assert devices.queue_item(dev.id, item.id).kind == kind


def test_set_kind_shows_in_the_queue(devices, library):
    dev, _ = devices.register("k2")
    item = _item(library, b"retag")
    entry = devices.queue_item(dev.id, item.id)
    assert entry.kind == "book"
    library.set_kind(item.id, "newspaper")
    assert devices.queue_item(dev.id, item.id).kind == "newspaper"
    assert all(e.kind == "newspaper" for e in devices.queue(dev.id))
