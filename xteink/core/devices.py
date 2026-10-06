"""DeviceService: registration, per-device keys, delivery queue, status."""

from __future__ import annotations

from .errors import AuthError, NotFoundError, ValidationError
from .keys import generate_key, parse_key, verify
from .models import Device, QueueEntry
from .store import Store, now

PREFIX = "xtd"

_Q = (
    "SELECT q.id, q.device_id, q.item_id, i.title, i.size, i.sha256, q.state,"
    " q.queued_at, q.delivered_at FROM queue q JOIN items i ON i.id = q.item_id"
)


def _device(r) -> Device:
    d = {k: r[k] for k in r.keys() if k != "key_hash"}
    d["mirror"] = bool(d["mirror"])
    return Device(**d)


def _entry(r) -> QueueEntry:
    return QueueEntry(**{k: r[k] for k in r.keys()})


class DeviceService:
    def __init__(self, store: Store) -> None:
        self.store = store

    def _get(self, c, device_id: int):
        row = c.execute("SELECT * FROM devices WHERE id = ?", (device_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"device {device_id} not found")
        return row

    def register(self, name: str, *, mirror: bool = False) -> tuple[Device, str]:
        """Create a device; the raw key is returned once and never stored."""
        if not name or not name.strip():
            raise ValidationError("name is required")
        raw, key_id, key_hash = generate_key(PREFIX)
        with self.store.connect() as c:
            cur = c.execute(
                "INSERT INTO devices (name, key_id, key_hash, mirror, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (name.strip(), key_id, key_hash, int(mirror), now()),
            )
            row = self._get(c, cur.lastrowid)
        return _device(row), raw

    def authenticate(self, raw: str) -> Device:
        """Verify a device key, update last_seen; AuthError if bad or revoked."""
        key_id = parse_key(raw, PREFIX)
        with self.store.connect() as c:
            row = c.execute("SELECT * FROM devices WHERE key_id = ?", (key_id,)).fetchone()
            if row is None or row["revoked_at"] or not verify(raw, row["key_hash"]):
                raise AuthError("invalid key")
            c.execute("UPDATE devices SET last_seen = ? WHERE id = ?", (now(), row["id"]))
            row = self._get(c, row["id"])
        return _device(row)

    def revoke_key(self, device_id: int) -> Device:
        with self.store.connect() as c:
            self._get(c, device_id)
            c.execute("UPDATE devices SET revoked_at = ? WHERE id = ?", (now(), device_id))
            return _device(self._get(c, device_id))

    def rotate_key(self, device_id: int) -> str:
        """Replace the device key (old one stops working); returns the new raw key."""
        raw, key_id, key_hash = generate_key(PREFIX)
        with self.store.connect() as c:
            self._get(c, device_id)
            c.execute(
                "UPDATE devices SET key_id = ?, key_hash = ?, revoked_at = NULL WHERE id = ?",
                (key_id, key_hash, device_id),
            )
        return raw

    def get(self, device_id: int) -> Device:
        with self.store.connect() as c:
            return _device(self._get(c, device_id))

    def list(self) -> list[Device]:
        with self.store.connect() as c:
            return [_device(r) for r in c.execute("SELECT * FROM devices ORDER BY id")]

    def set_mirror(self, device_id: int, mirror: bool) -> Device:
        with self.store.connect() as c:
            self._get(c, device_id)
            c.execute("UPDATE devices SET mirror = ? WHERE id = ?", (int(mirror), device_id))
            return _device(self._get(c, device_id))

    def queue_item(self, device_id: int, item_id: int) -> QueueEntry:
        """Queue an item for a device (idempotent)."""
        with self.store.connect() as c:
            self._get(c, device_id)
            if c.execute("SELECT 1 FROM items WHERE id = ?", (item_id,)).fetchone() is None:
                raise NotFoundError(f"item {item_id} not found")
            c.execute(
                "INSERT OR IGNORE INTO queue (device_id, item_id, queued_at) VALUES (?, ?, ?)",
                (device_id, item_id, now()),
            )
            row = c.execute(
                _Q + " WHERE q.device_id = ? AND q.item_id = ?", (device_id, item_id)
            ).fetchone()
        return _entry(row)

    def queue(self, device_id: int, *, state: str | None = "queued") -> list[QueueEntry]:
        """Entries for a device; state=None returns every state."""
        sql, params = _Q + " WHERE q.device_id = ?", [device_id]
        if state is not None:
            sql += " AND q.state = ?"
            params.append(state)
        with self.store.connect() as c:
            self._get(c, device_id)
            return [_entry(r) for r in c.execute(sql + " ORDER BY q.id", params)]

    def mark_delivered(self, device_id: int, item_id: int, sha256: str) -> QueueEntry:
        """Device ACK: sha256 must match the item's, else ValidationError."""
        with self.store.connect() as c:
            row = c.execute(
                _Q + " WHERE q.device_id = ? AND q.item_id = ?", (device_id, item_id)
            ).fetchone()
            if row is None:
                raise NotFoundError(f"item {item_id} is not queued for device {device_id}")
            if sha256 != row["sha256"]:
                raise ValidationError("sha256 mismatch")
            c.execute(
                "UPDATE queue SET state = 'delivered', delivered_at = ? WHERE id = ?",
                (now(), row["id"]),
            )
            row = c.execute(_Q + " WHERE q.id = ?", (row["id"],)).fetchone()
        return _entry(row)

    def report_status(
        self,
        device_id: int,
        *,
        last_sync_result: str | None = None,
        free_sd_bytes: int | None = None,
        firmware_version: str | None = None,
        last_error: str | None = None,
    ) -> Device:
        """Record a device status report (also bumps last_seen)."""
        with self.store.connect() as c:
            self._get(c, device_id)
            c.execute(
                "UPDATE devices SET last_seen = ?, last_sync_result = ?, free_sd_bytes = ?,"
                " firmware_version = ?, last_error = ? WHERE id = ?",
                (now(), last_sync_result, free_sd_bytes, firmware_version, last_error, device_id),
            )
            return _device(self._get(c, device_id))

    def status(self, device_id: int) -> Device:
        return self.get(device_id)
