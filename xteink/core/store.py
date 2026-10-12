"""SQLite + content-addressed file storage under XTEINK_DATA_DIR."""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator

DATA_DIR_ENV = "XTEINK_DATA_DIR"
DEFAULT_DATA_DIR = "~/.local/share/xteink"
DB_NAME = "library.db"

# Schema version 1: the issue-1 layout. Kept exactly as it shipped (CREATE TABLE IF NOT
# EXISTS), so a fresh database and an issue-1 database start from the same point. Every
# later change is a numbered step in _MIGRATIONS, never an edit here.
_SCHEMA = """
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

# Step N brings a database from user_version N-1 to N. A step is a tuple of single SQL
# statements run in one transaction together with the user_version bump, so a step is
# applied whole or not at all and never twice. Append new steps; never edit old ones.
_MIGRATIONS: tuple[tuple[str, ...], ...] = (
    # 1: issue-1 baseline. Databases written before versioning (user_version 0) already
    # have these tables; the IF NOT EXISTS schema above created them on fresh ones.
    (),
    # 2: OTA firmware + daily-run status. Images live in their own table, never in items
    # (items.kind stays CHECK-constrained to book/article); blobs share files/<aa>/<sha>.
    (
        "CREATE TABLE firmware ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " version TEXT NOT NULL,"
        " sha256 TEXT NOT NULL UNIQUE,"
        " size INTEGER NOT NULL,"
        " board TEXT NOT NULL,"
        " fork_commit TEXT,"
        " source_pr TEXT,"
        " created_at TEXT NOT NULL)",
        "CREATE TABLE firmware_rollbacks ("
        " device_id INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,"
        " firmware_id INTEGER NOT NULL REFERENCES firmware(id) ON DELETE CASCADE,"
        " rolled_back_at TEXT NOT NULL,"
        " PRIMARY KEY (device_id, firmware_id))",
        "ALTER TABLE devices ADD COLUMN offered_firmware_id INTEGER"
        " REFERENCES firmware(id) ON DELETE SET NULL",
        "ALTER TABLE devices ADD COLUMN last_run_at TEXT",
        "ALTER TABLE devices ADD COLUMN last_run_trigger TEXT",
        "ALTER TABLE devices ADD COLUMN last_fw_outcome TEXT",
        "ALTER TABLE devices ADD COLUMN last_content_outcome TEXT",
    ),
)

SCHEMA_VERSION = len(_MIGRATIONS)


def _migrate(conn: sqlite3.Connection) -> None:
    """Apply every pending step; a no-op on an up-to-date database.

    ``BEGIN IMMEDIATE`` takes the write lock before user_version is read, so two
    processes opening the same old database cannot both run a step.
    """
    conn.executescript(_SCHEMA)
    conn.isolation_level = None  # manage the transaction by hand
    conn.execute("BEGIN IMMEDIATE")
    try:
        current = conn.execute("PRAGMA user_version").fetchone()[0]
        if current > SCHEMA_VERSION:
            raise RuntimeError(
                f"{DB_NAME} has schema version {current}, newer than this xteink"
                f" ({SCHEMA_VERSION}); upgrade xteink"
            )
        for version in range(current + 1, SCHEMA_VERSION + 1):
            for statement in _MIGRATIONS[version - 1]:
                conn.execute(statement)
        if current != SCHEMA_VERSION:
            # PRAGMA takes no bound parameters; SCHEMA_VERSION is an int constant.
            conn.execute(f"PRAGMA user_version = {int(SCHEMA_VERSION)}")
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class Store:
    """Owns the data directory: ``library.db`` plus ``files/<aa>/<sha256>``."""

    def __init__(self, data_dir: str | os.PathLike[str] | None = None) -> None:
        raw = data_dir or os.environ.get(DATA_DIR_ENV) or DEFAULT_DATA_DIR
        self.data_dir = Path(raw).expanduser()
        self.files_dir = self.data_dir / "files"
        self.db_path = self.data_dir / DB_NAME
        self.files_dir.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=30)
        try:
            _migrate(conn)
        finally:
            conn.close()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """Short-lived connection (thread-safe use); commits on success."""
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def blob_path(self, sha256: str) -> Path:
        return self.files_dir / sha256[:2] / sha256
