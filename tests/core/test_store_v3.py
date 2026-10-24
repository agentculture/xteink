"""Schema v3: the items table takes four kinds; a backup precedes every migration.

Plan kind-transcript, task t1 (frame c2/h2/c22/h20).
"""

import sqlite3

import pytest

from tests.core.test_firmware import _dump, _issue1_db
from xteink.core import Store
from xteink.core.store import _MIGRATIONS, DB_NAME, SCHEMA_VERSION

TS = "2026-10-24T00:00:00+00:00"


def _v2_db(data_dir):
    """The issue-1 fixture (items, devices, queue rows) brought to user_version 2."""
    _issue1_db(data_dir)
    conn = sqlite3.connect(data_dir / DB_NAME)
    try:
        for step in _MIGRATIONS[:2]:
            for statement in step:
                conn.execute(statement)
        conn.execute("PRAGMA user_version = 2")
        conn.commit()
    finally:
        conn.close()
    return data_dir / DB_NAME


def _insert_item(conn, sha, kind):
    return conn.execute(
        "INSERT INTO items (sha256, kind, title, format, size, created_at)"
        " VALUES (?, ?, 't', 'epub', 1, ?)",
        (sha, kind, TS),
    ).lastrowid


def test_schema_version_is_3():
    assert SCHEMA_VERSION == 3


def test_v2_db_migrates_with_items_and_queue_unchanged(tmp_path):
    data_dir = tmp_path / "data"
    db = _v2_db(data_dir)
    before_items = _dump(db, "items")
    before_queue = _dump(db, "queue")
    max_id = max(r[0] for r in before_items)

    store = Store(data_dir)

    conn = sqlite3.connect(store.db_path)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 3
    finally:
        conn.close()
    assert _dump(db, "items") == before_items
    assert _dump(db, "queue") == before_queue
    with store.connect() as conn:
        assert _insert_item(conn, "c" * 64, "book") == max_id + 1


def test_rebuild_keeps_the_autoincrement_high_water_mark(tmp_path):
    """An id freed by a delete before the migration is never handed out again."""
    data_dir = tmp_path / "data"
    db = _v2_db(data_dir)
    conn = sqlite3.connect(db)
    conn.execute("DELETE FROM queue WHERE item_id = 2")
    conn.execute("DELETE FROM items WHERE id = 2")
    conn.commit()
    conn.close()

    store = Store(data_dir)

    with store.connect() as conn:
        assert _insert_item(conn, "c" * 64, "book") == 3


@pytest.mark.parametrize("old", ["v0", "v1"])
def test_v0_and_v1_dbs_migrate_through_step_3(tmp_path, old):
    data_dir = tmp_path / "data"
    _issue1_db(data_dir)
    db = data_dir / DB_NAME
    if old == "v1":
        conn = sqlite3.connect(db)
        conn.execute("PRAGMA user_version = 1")
        conn.close()
    before = _dump(db, "items")

    store = Store(data_dir)

    assert _dump(db, "items") == before
    with store.connect() as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 3
        _insert_item(conn, "t" * 64, "transcript")


@pytest.fixture
def migrated(tmp_path):
    data_dir = tmp_path / "data"
    _v2_db(data_dir)
    return Store(data_dir)


@pytest.mark.parametrize("kind", ["book", "article", "transcript", "newspaper"])
def test_four_kinds_are_accepted(migrated, kind):
    with migrated.connect() as conn:
        _insert_item(conn, "c" * 64, kind)


@pytest.mark.parametrize("kind", ["firmware", "pdf", ""])
def test_other_kinds_are_refused(migrated, kind):
    with migrated.connect() as conn:
        with pytest.raises(sqlite3.IntegrityError):
            _insert_item(conn, "c" * 64, kind)


def test_foreign_keys_hold_after_the_rebuild(migrated):
    with migrated.connect() as conn:
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        assert conn.execute("SELECT COUNT(*) FROM queue WHERE item_id = 1").fetchone()[0] == 1
        conn.execute("DELETE FROM items WHERE id = 1")
        assert conn.execute("SELECT COUNT(*) FROM queue WHERE item_id = 1").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM queue").fetchone()[0] == 1


def test_queue_still_refuses_an_unknown_item(migrated):
    with migrated.connect() as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO queue (device_id, item_id, queued_at) VALUES (1, 999, ?)", (TS,)
            )


# --- pre-migration backup (c22/h20) ---------------------------------------------------


def test_pending_step_writes_a_backup_of_the_old_db(tmp_path):
    data_dir = tmp_path / "data"
    db = _v2_db(data_dir)
    before = _dump(db, "items")

    Store(data_dir)

    bak = data_dir / f"{DB_NAME}.v2.bak"
    assert bak.is_file()
    conn = sqlite3.connect(bak)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
        items_sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='items'"
        ).fetchone()[0]
        assert "CHECK (kind IN ('book', 'article'))" in items_sql
    finally:
        conn.close()
    assert _dump(bak, "items") == before


def test_v0_db_backup_is_named_for_version_0(tmp_path):
    data_dir = tmp_path / "data"
    _issue1_db(data_dir)
    before = _dump(data_dir / DB_NAME, "items")

    Store(data_dir)

    bak = data_dir / f"{DB_NAME}.v0.bak"
    assert _dump(bak, "items") == before
    conn = sqlite3.connect(bak)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 0
    finally:
        conn.close()


def _baks(data_dir):
    return sorted(p.name for p in data_dir.glob("*.bak"))


def test_up_to_date_db_writes_no_backup(tmp_path):
    data_dir = tmp_path / "data"
    _v2_db(data_dir)
    Store(data_dir)
    (data_dir / f"{DB_NAME}.v2.bak").unlink()

    Store(data_dir)

    assert _baks(data_dir) == []


def test_brand_new_db_writes_no_backup(tmp_path):
    data_dir = tmp_path / "data"
    Store(data_dir)
    assert _baks(data_dir) == []
    Store(data_dir)
    assert _baks(data_dir) == []
