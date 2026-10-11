"""FirmwareStore: uploaded device images, per-device offers and rollback memory.

Images get their own ``firmware`` table and never go into ``items`` (whose ``kind`` is
book/article only). The bytes reuse the content-addressed ``files/<aa>/<sha256>`` store.
Validating that the bytes are a real image for the board is the caller's job (see the
ESP image header check); this module only stores and tracks them.
"""

from __future__ import annotations

import hashlib
import sqlite3
import uuid
from pathlib import Path

from .errors import NotFoundError, ValidationError
from .models import AddFirmwareResult, Firmware, OfferAllResult
from .store import Store, now

_SEL = (
    "SELECT f.id, f.version, f.sha256, f.size, f.board, f.fork_commit, f.source_pr,"
    " f.created_at FROM firmware f"
)


def _fw(r) -> Firmware:
    return Firmware(**{k: r[k] for k in r.keys()})


def _opt(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


class FirmwareStore:
    def __init__(self, store: Store) -> None:
        self.store = store

    # --- lookups ------------------------------------------------------------------

    @staticmethod
    def _get(c, firmware_id: int):
        row = c.execute(_SEL + " WHERE f.id = ?", (firmware_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"firmware {firmware_id} not found")
        return row

    @staticmethod
    def _device(c, device_id: int):
        row = c.execute(
            "SELECT id, revoked_at, offered_firmware_id FROM devices WHERE id = ?", (device_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"device {device_id} not found")
        return row

    @staticmethod
    def _rolled_back(c, device_id: int, firmware_id: int) -> bool:
        return (
            c.execute(
                "SELECT 1 FROM firmware_rollbacks WHERE device_id = ? AND firmware_id = ?",
                (device_id, firmware_id),
            ).fetchone()
            is not None
        )

    # --- images -------------------------------------------------------------------

    def add(
        self,
        data: bytes,
        *,
        version: str,
        board: str,
        fork_commit: str | None = None,
        source_pr: str | None = None,
    ) -> AddFirmwareResult:
        """Store an image. Dedups by sha256: re-uploading the same bytes returns the
        existing row (``created=False``) with its original metadata."""
        if not isinstance(data, bytes):
            raise ValidationError("data must be bytes")
        if not data:
            raise ValidationError("firmware image is empty")
        if not version or not version.strip():
            raise ValidationError("version is required")
        if not board or not board.strip():
            raise ValidationError("board is required")
        sha = hashlib.sha256(data).hexdigest()
        with self.store.connect() as c:
            row = c.execute(_SEL + " WHERE f.sha256 = ?", (sha,)).fetchone()
            if row is not None:
                return AddFirmwareResult(_fw(row), False)
            blob = self.store.blob_path(sha)
            blob.parent.mkdir(parents=True, exist_ok=True)
            if not blob.exists():
                tmp = blob.with_name(f"{blob.name}.{uuid.uuid4().hex}.tmp")
                tmp.write_bytes(data)
                tmp.replace(blob)
            try:
                cur = c.execute(
                    "INSERT INTO firmware (version, sha256, size, board, fork_commit,"
                    " source_pr, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        version.strip(),
                        sha,
                        len(data),
                        board.strip().lower(),
                        _opt(fork_commit),
                        _opt(source_pr),
                        now(),
                    ),
                )
            except sqlite3.IntegrityError:
                # A concurrent upload of the same bytes committed first.
                row = c.execute(_SEL + " WHERE f.sha256 = ?", (sha,)).fetchone()
                if row is None:
                    raise
                return AddFirmwareResult(_fw(row), False)
            row = self._get(c, cur.lastrowid)
        return AddFirmwareResult(_fw(row), True)

    def get(self, firmware_id: int) -> Firmware:
        with self.store.connect() as c:
            return _fw(self._get(c, firmware_id))

    def list(self) -> list[Firmware]:
        with self.store.connect() as c:
            return [_fw(r) for r in c.execute(_SEL + " ORDER BY f.id")]

    def file_path(self, firmware_id: int) -> Path:
        return self.store.blob_path(self.get(firmware_id).sha256)

    # --- offers -------------------------------------------------------------------

    def offer(self, device_id: int, firmware_id: int) -> Firmware:
        """Offer an image to one device, replacing any previous offer.

        ValidationError if the device is revoked or has already rolled this image back.
        """
        with self.store.connect() as c:
            dev = self._device(c, device_id)
            fw = _fw(self._get(c, firmware_id))
            if dev["revoked_at"]:
                raise ValidationError(f"device {device_id} is revoked")
            if self._rolled_back(c, device_id, firmware_id):
                raise ValidationError(
                    f"device {device_id} rolled back firmware {firmware_id} ({fw.version});"
                    " it is not offered again"
                )
            c.execute(
                "UPDATE devices SET offered_firmware_id = ? WHERE id = ?",
                (firmware_id, device_id),
            )
        return fw

    def offer_all(self, firmware_id: int) -> OfferAllResult:
        """Offer an image to every provisioned (non-revoked) device that has not rolled
        it back. Skipped devices keep whatever offer they had."""
        offered, revoked, rolled = [], [], []
        with self.store.connect() as c:
            fw = _fw(self._get(c, firmware_id))
            for dev in c.execute("SELECT id, revoked_at FROM devices ORDER BY id").fetchall():
                if dev["revoked_at"]:
                    revoked.append(dev["id"])
                elif self._rolled_back(c, dev["id"], firmware_id):
                    rolled.append(dev["id"])
                else:
                    offered.append(dev["id"])
            c.executemany(
                "UPDATE devices SET offered_firmware_id = ? WHERE id = ?",
                [(firmware_id, d) for d in offered],
            )
        return OfferAllResult(fw, tuple(offered), tuple(revoked), tuple(rolled))

    def offered(self, device_id: int) -> Firmware | None:
        """The image currently offered to a device, or None."""
        with self.store.connect() as c:
            dev = self._device(c, device_id)
            if dev["offered_firmware_id"] is None:
                return None
            return _fw(self._get(c, dev["offered_firmware_id"]))

    # --- rollbacks ----------------------------------------------------------------

    def record_rollback(self, device_id: int, firmware_id: int) -> None:
        """Remember that a device rolled an image back (idempotent).

        If that image is the device's current offer, the offer is withdrawn so it is
        not offered again; an offer of a different image is left alone.
        """
        with self.store.connect() as c:
            self._device(c, device_id)
            self._get(c, firmware_id)
            c.execute(
                "INSERT INTO firmware_rollbacks (device_id, firmware_id, rolled_back_at)"
                " VALUES (?, ?, ?) ON CONFLICT (device_id, firmware_id) DO NOTHING",
                (device_id, firmware_id, now()),
            )
            c.execute(
                "UPDATE devices SET offered_firmware_id = NULL"
                " WHERE id = ? AND offered_firmware_id = ?",
                (device_id, firmware_id),
            )

    def rolled_back(self, device_id: int) -> list[Firmware]:
        """Images this device has rolled back, oldest upload first."""
        with self.store.connect() as c:
            self._device(c, device_id)
            rows = c.execute(
                _SEL + " JOIN firmware_rollbacks r ON r.firmware_id = f.id"
                " WHERE r.device_id = ? ORDER BY f.id",
                (device_id,),
            )
            return [_fw(r) for r in rows]

    def rollbacks_of(self, firmware_id: int) -> list[dict]:
        """Devices that rolled this image back, oldest first (id, name, rolled_back_at)."""
        with self.store.connect() as c:
            self._get(c, firmware_id)
            rows = c.execute(
                "SELECT d.id AS device_id, d.name AS device_name, r.rolled_back_at"
                " FROM firmware_rollbacks r JOIN devices d ON d.id = r.device_id"
                " WHERE r.firmware_id = ? ORDER BY r.rolled_back_at, d.id",
                (firmware_id,),
            )
            return [dict(r) for r in rows]
