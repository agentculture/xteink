"""FirmwareStore + the versioned schema migration (plan task t3; frame c2/h11)."""

import hashlib
import sqlite3

import pytest

from xteink.core import FirmwareStore, NotFoundError, Store, ValidationError
from xteink.core.store import SCHEMA_VERSION

# The library.db schema exactly as issue 1 shipped it (xteink/core/store.py before the
# OTA work), copied verbatim so the migration is tested against a real old layout.
ISSUE1_SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sha256 TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL CHECK (kind IN ('book', 'article')),
    title TEXT NOT NULL,
    author TEXT NOT NULL DEFAULT '',
    format TEXT NOT NULL,
    size INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS devices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    key_id TEXT NOT NULL UNIQUE,
    key_hash TEXT NOT NULL,
    mirror INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    revoked_at TEXT,
    last_seen TEXT,
    last_sync_result TEXT,
    free_sd_bytes INTEGER,
    firmware_version TEXT,
    last_error TEXT
);
CREATE TABLE IF NOT EXISTS queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    state TEXT NOT NULL DEFAULT 'queued' CHECK (state IN ('queued', 'delivered')),
    queued_at TEXT NOT NULL,
    delivered_at TEXT,
    UNIQUE (device_id, item_id)
);
CREATE TABLE IF NOT EXISTS api_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    key_id TEXT NOT NULL UNIQUE,
    key_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    revoked_at TEXT,
    last_used TEXT
);
"""

NEW_DEVICE_COLUMNS = {
    "offered_firmware_id",
    "last_run_at",
    "last_run_trigger",
    "last_fw_outcome",
    "last_content_outcome",
}
IMAGE = b"\xe9" + b"\x00" * 63 + b"fake-image"


@pytest.fixture
def firmware(store):
    return FirmwareStore(store)


def _issue1_db(data_dir):
    """An issue-1-era library.db (user_version 0) with items, devices and queue rows."""
    data_dir.mkdir(parents=True)
    conn = sqlite3.connect(data_dir / "library.db")
    conn.executescript(ISSUE1_SCHEMA)
    ts = "2026-10-01T00:00:00+00:00"
    conn.executemany(
        "INSERT INTO items (sha256, kind, title, author, format, size, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            ("a" * 64, "book", "Book A", "Someone", "epub", 10, ts),
            ("b" * 64, "article", "Article B", "", "html", 20, ts),
        ],
    )
    conn.executemany(
        "INSERT INTO devices (name, key_id, key_hash, mirror, created_at, revoked_at,"
        " last_seen, last_sync_result, free_sd_bytes, firmware_version, last_error)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            ("x3", "k1", "h1", 1, ts, None, ts, "ok", 123, "1.6.5-dev", None),
            ("old", "k2", "h2", 0, ts, ts, None, None, None, None, "gone"),
        ],
    )
    conn.executemany(
        "INSERT INTO queue (device_id, item_id, state, queued_at, delivered_at)"
        " VALUES (?, ?, ?, ?, ?)",
        [(1, 1, "delivered", ts, ts), (1, 2, "queued", ts, None)],
    )
    conn.commit()
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 0
    conn.close()


def _dump(db_path, table):
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(f"SELECT * FROM {table} ORDER BY id").fetchall()  # nosec B608
    finally:
        conn.close()


def _columns(conn, table):
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


# --- migration (h11) -------------------------------------------------------------


def test_issue1_db_migrates_with_rows_intact(tmp_path):
    data_dir = tmp_path / "data"
    _issue1_db(data_dir)
    db = data_dir / "library.db"
    before = {t: _dump(db, t) for t in ("items", "devices", "queue")}

    store = Store(data_dir)

    conn = sqlite3.connect(store.db_path)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"firmware", "firmware_rollbacks"} <= tables
        assert _columns(conn, "firmware") == {
            "id",
            "version",
            "sha256",
            "size",
            "board",
            "fork_commit",
            "source_pr",
            "created_at",
        }
        assert {"device_id", "firmware_id"} <= _columns(conn, "firmware_rollbacks")
        assert NEW_DEVICE_COLUMNS <= _columns(conn, "devices")
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        conn.close()

    after = {t: _dump(db, t) for t in ("items", "devices", "queue")}
    assert after["items"] == before["items"]
    assert after["queue"] == before["queue"]
    old_width = len(before["devices"][0])
    assert [r[:old_width] for r in after["devices"]] == before["devices"]
    assert all(r[old_width:] == (None,) * len(NEW_DEVICE_COLUMNS) for r in after["devices"])


def test_migrated_issue1_db_works_through_the_services(tmp_path):
    from xteink.core import DeviceService, LibraryService

    data_dir = tmp_path / "data"
    _issue1_db(data_dir)
    store = Store(data_dir)
    devices = DeviceService(store)
    assert [d.name for d in devices.list()] == ["x3", "old"]
    x3 = devices.get(1)
    assert x3.firmware_version == "1.6.5-dev"
    assert x3.offered_firmware_id is None
    assert x3.last_run_at is None
    assert [e.item_id for e in devices.queue(1, state=None)] == [1, 2]
    assert [i.title for i in LibraryService(store).list()] == ["Book A", "Article B"]

    fw = FirmwareStore(store)
    image = fw.add(IMAGE, version="1.6.5-dev-x", board="x3").firmware
    result = fw.offer_all(image.id)
    assert result.offered == (1,)  # device 2 is revoked


def test_migration_is_idempotent(tmp_path):
    data_dir = tmp_path / "data"
    _issue1_db(data_dir)
    store = Store(data_dir)
    fw = FirmwareStore(store)
    image = fw.add(IMAGE, version="v1", board="x3").firmware
    fw.offer(1, image.id)
    schema = _dump_schema(store.db_path)

    again = Store(data_dir)  # a second open must be a no-op, not a duplicate ALTER

    assert _dump_schema(again.db_path) == schema
    assert FirmwareStore(again).get(image.id) == image
    from xteink.core import DeviceService

    assert DeviceService(again).get(1).offered_firmware_id == image.id


def test_fresh_db_gets_the_same_schema_as_a_migrated_one(tmp_path):
    _issue1_db(tmp_path / "old")
    migrated = _dump_schema(Store(tmp_path / "old").db_path)
    fresh = _dump_schema(Store(tmp_path / "new").db_path)
    assert fresh == migrated


def test_newer_schema_than_this_code_is_refused(tmp_path):
    store = Store(tmp_path / "data")
    conn = sqlite3.connect(store.db_path)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
    conn.close()
    with pytest.raises(RuntimeError, match="newer"):
        Store(tmp_path / "data")


def _dump_schema(db_path):
    """Version, object names and per-table columns.

    Raw ``sqlite_master.sql`` is not compared: ALTER TABLE ADD COLUMN leaves different
    text than a fresh CREATE, while the resulting columns are the same.
    """
    conn = sqlite3.connect(db_path)
    try:
        objects = conn.execute(
            "SELECT type, name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
        ).fetchall()
        cols = {
            name: [tuple(r) for r in conn.execute(f"PRAGMA table_info({name})")]
            for kind, name in objects
            if kind == "table"
        }
        version = conn.execute("PRAGMA user_version").fetchone()[0]
    finally:
        conn.close()
    return version, set(objects), cols


# --- items hold library kinds only, never firmware ------------------------------------------------


def test_firmware_never_goes_into_items(store, firmware):
    firmware.add(IMAGE, version="v1", board="x3")
    conn = sqlite3.connect(store.db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 0
        items_sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='items'"
        ).fetchone()[0]
        assert "CHECK (kind IN ('book', 'article', 'transcript', 'newspaper'))" in items_sql
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO items (sha256, kind, title, format, size, created_at)"
                " VALUES ('c', 'firmware', 't', 'bin', 1, 'now')"
            )
    finally:
        conn.close()


# --- add / list / get ------------------------------------------------------------


def test_add_stores_blob_in_the_sha256_store(store, firmware):
    res = firmware.add(
        IMAGE, version="1.6.5-dev-a", board="x3", fork_commit="abc123", source_pr="https://pr/1"
    )
    fw = res.firmware
    assert res.created is True
    assert fw.sha256 == hashlib.sha256(IMAGE).hexdigest()
    assert fw.size == len(IMAGE)
    assert (fw.version, fw.board, fw.fork_commit, fw.source_pr) == (
        "1.6.5-dev-a",
        "x3",
        "abc123",
        "https://pr/1",
    )
    assert store.blob_path(fw.sha256).read_bytes() == IMAGE
    assert firmware.file_path(fw.id) == store.blob_path(fw.sha256)
    assert firmware.get(fw.id) == fw
    assert firmware.list() == [fw]


def test_add_dedups_by_sha256(firmware):
    first = firmware.add(IMAGE, version="v1", board="x3")
    again = firmware.add(IMAGE, version="v1-again", board="x3")
    assert again.created is False
    assert again.firmware == first.firmware
    assert len(firmware.list()) == 1


@pytest.mark.parametrize(
    "data, kwargs",
    [
        ("not-bytes", {"version": "v", "board": "x3"}),
        (b"", {"version": "v", "board": "x3"}),
        (IMAGE, {"version": " ", "board": "x3"}),
        (IMAGE, {"version": "v", "board": ""}),
    ],
)
def test_add_rejects_bad_input(firmware, data, kwargs):
    with pytest.raises(ValidationError):
        firmware.add(data, **kwargs)


def test_get_missing(firmware):
    with pytest.raises(NotFoundError):
        firmware.get(42)


# --- offer / rollback --------------------------------------------------------------


def test_offer_to_a_device(devices, firmware):
    dev, _ = devices.register("x3")
    fw = firmware.add(IMAGE, version="v1", board="x3").firmware
    assert firmware.offered(dev.id) is None
    firmware.offer(dev.id, fw.id)
    assert firmware.offered(dev.id) == fw
    assert devices.get(dev.id).offered_firmware_id == fw.id


def test_offer_unknown_device_or_firmware(devices, firmware):
    dev, _ = devices.register("x3")
    fw = firmware.add(IMAGE, version="v1", board="x3").firmware
    with pytest.raises(NotFoundError):
        firmware.offer(999, fw.id)
    with pytest.raises(NotFoundError):
        firmware.offer(dev.id, 999)


def test_offer_to_revoked_device_is_a_user_error(devices, firmware):
    dev, _ = devices.register("x3")
    devices.revoke_key(dev.id)
    fw = firmware.add(IMAGE, version="v1", board="x3").firmware
    with pytest.raises(ValidationError, match="revoked"):
        firmware.offer(dev.id, fw.id)


def test_offering_a_rolled_back_firmware_is_a_user_error(devices, firmware):
    dev, _ = devices.register("x3")
    fw = firmware.add(IMAGE, version="v1", board="x3").firmware
    firmware.offer(dev.id, fw.id)
    firmware.record_rollback(dev.id, fw.id)
    assert firmware.offered(dev.id) is None  # the rolled-back offer is withdrawn
    assert firmware.rolled_back(dev.id) == [fw]
    with pytest.raises(ValidationError, match="rolled back"):
        firmware.offer(dev.id, fw.id)
    assert firmware.offered(dev.id) is None


def test_record_rollback_is_idempotent_and_keeps_other_offers(devices, firmware):
    dev, _ = devices.register("x3")
    bad = firmware.add(IMAGE, version="bad", board="x3").firmware
    good = firmware.add(IMAGE + b"2", version="good", board="x3").firmware
    firmware.offer(dev.id, good.id)
    firmware.record_rollback(dev.id, bad.id)
    firmware.record_rollback(dev.id, bad.id)
    assert firmware.rolled_back(dev.id) == [bad]
    assert firmware.offered(dev.id) == good  # a rollback of another build keeps the offer
    with pytest.raises(NotFoundError):
        firmware.record_rollback(999, bad.id)
    with pytest.raises(NotFoundError):
        firmware.record_rollback(dev.id, 999)


def test_offer_all_skips_revoked_and_rolled_back(devices, firmware):
    a, _ = devices.register("a")
    b, _ = devices.register("b")
    c, _ = devices.register("c")
    d, _ = devices.register("d")
    devices.revoke_key(b.id)
    fw = firmware.add(IMAGE, version="v1", board="x3").firmware
    firmware.record_rollback(c.id, fw.id)

    result = firmware.offer_all(fw.id)

    assert result.firmware == fw
    assert result.offered == (a.id, d.id)
    assert result.skipped_revoked == (b.id,)
    assert result.skipped_rolled_back == (c.id,)
    assert firmware.offered(a.id) == fw
    assert firmware.offered(d.id) == fw
    assert firmware.offered(b.id) is None
    assert firmware.offered(c.id) is None


def test_dry_run_offers_check_the_same_rules_and_write_nothing(devices, firmware):
    a, _ = devices.register("a")
    b, _ = devices.register("b")
    c, _ = devices.register("c")
    devices.revoke_key(b.id)
    fw = firmware.add(IMAGE, version="v1", board="x3").firmware
    firmware.record_rollback(c.id, fw.id)

    result = firmware.offer_all(fw.id, dry_run=True)
    assert (result.offered, result.skipped_revoked, result.skipped_rolled_back) == (
        (a.id,),
        (b.id,),
        (c.id,),
    )
    assert firmware.offered(a.id) is None

    assert firmware.offer(a.id, fw.id, dry_run=True) == fw
    assert firmware.offered(a.id) is None
    with pytest.raises(ValidationError, match="revoked"):
        firmware.offer(b.id, fw.id, dry_run=True)
    with pytest.raises(ValidationError, match="rolled back"):
        firmware.offer(c.id, fw.id, dry_run=True)


def test_offer_all_unknown_firmware(firmware):
    with pytest.raises(NotFoundError):
        firmware.offer_all(7)


def test_deleting_a_device_drops_its_rollbacks(store, devices, firmware):
    dev, _ = devices.register("x3")
    fw = firmware.add(IMAGE, version="v1", board="x3").firmware
    firmware.record_rollback(dev.id, fw.id)
    with store.connect() as c:
        c.execute("DELETE FROM devices WHERE id = ?", (dev.id,))
        assert c.execute("SELECT COUNT(*) FROM firmware_rollbacks").fetchone()[0] == 0
