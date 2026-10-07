"""A fake Xteink reader that speaks device protocol v1 (docs/device-protocol.md).

It holds an in-memory "SD card", reports free space, can drop a download
mid-stream and resume it with an HTTP ``Range`` request, and acks by sha256.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

PROTOCOL = "1"


@dataclass
class SdFile:
    """A file on the fake SD card. ``sha256`` is what the server delivered."""

    data: bytes
    sha256: str | None = None  # None = user-sideloaded (never reported in inventory)

    @property
    def unmodified(self) -> bool:
        return self.sha256 is not None and hashlib.sha256(self.data).hexdigest() == self.sha256


@dataclass
class SyncResult:
    delivered: list[int] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    resumed: list[int] = field(default_factory=list)


class FakeDevice:
    def __init__(
        self,
        client,
        key: str,
        *,
        sd_capacity: int = 10_000_000,
        firmware_version: str = "xteink-fw 0.1.0",
        protocol: str = PROTOCOL,
    ) -> None:
        self.client = client
        self.key = key
        self.sd_capacity = sd_capacity
        self.firmware_version = firmware_version
        self.protocol = protocol
        self.sd: dict[str, SdFile] = {}  # filename -> file
        self.partial: dict[int, bytearray] = {}  # item id -> bytes received so far
        self.last_error: str | None = None
        self.last_sync_result: str | None = None

    # -- helpers ------------------------------------------------------------

    def headers(self, **extra: str) -> dict:
        h = {"Authorization": f"Bearer {self.key}", "X-Xteink-Protocol": self.protocol}
        h.update(extra)
        return h

    @property
    def free_sd_bytes(self) -> int:
        used = sum(len(f.data) for f in self.sd.values())
        used += sum(len(p) for p in self.partial.values())
        return self.sd_capacity - used

    def inventory(self) -> list[dict]:
        """Server-delivered files only; sideloaded files are never reported."""
        return [
            {"sha256": f.sha256, "unmodified": f.unmodified}
            for f in self.sd.values()
            if f.sha256 is not None
        ]

    def sideload(self, name: str, data: bytes) -> None:
        self.sd[name] = SdFile(data)

    # -- protocol calls -----------------------------------------------------

    def post_status(self):
        return self.client.post(
            "/api/device/status",
            headers=self.headers(),
            json={
                "free_sd_bytes": self.free_sd_bytes,
                "firmware_version": self.firmware_version,
                "last_error": self.last_error,
                "last_sync_result": self.last_sync_result,
                "inventory": self.inventory(),
            },
        )

    def get_queue(self):
        return self.client.get("/api/device/queue", headers=self.headers())

    def download(self, item: dict, *, drop_after: int | None = None) -> tuple[bytes | None, bool]:
        """Fetch ``item['url']``, resuming from any partial bytes already held.

        ``drop_after`` simulates the connection dying after that many body bytes:
        the partial bytes are kept and ``(None, False)`` is returned.
        Returns ``(data, resumed)`` on completion.
        """
        buf = self.partial.setdefault(item["id"], bytearray())
        resumed = len(buf) > 0
        headers = self.headers()
        if resumed:
            headers["Range"] = f"bytes={len(buf)}-"
        with self.client.stream("GET", item["url"], headers=headers) as r:
            expected = 206 if resumed else 200
            if r.status_code != expected:
                raise AssertionError(f"download {item['url']}: {r.status_code} {r.read()!r}")
            if resumed:
                total = item["size"]
                assert r.headers["content-range"] == f"bytes {len(buf)}-{total - 1}/{total}"
            for chunk in r.iter_bytes(chunk_size=64):
                if drop_after is not None and len(buf) + len(chunk) >= drop_after:
                    buf.extend(chunk[: drop_after - len(buf)])
                    return None, False  # connection dropped mid-stream
                buf.extend(chunk)
        data = bytes(self.partial.pop(item["id"]))
        return data, resumed

    def ack(self, item_id: int, sha256: str):
        return self.client.post(
            "/api/device/ack", headers=self.headers(), json={"item_id": item_id, "sha256": sha256}
        )

    # -- full flow ----------------------------------------------------------

    def sync(self, *, drop_after: dict[int, int] | None = None) -> SyncResult:
        """status -> queue -> download (resume on drop) -> sha256 ack -> deletes -> status."""
        drop_after = dict(drop_after or {})
        result = SyncResult()
        r = self.post_status()
        r.raise_for_status()
        r = self.get_queue()
        r.raise_for_status()
        q = r.json()
        assert q["protocol"] == PROTOCOL
        result.skipped = q["skipped"]
        for item in q["items"]:
            data, resumed = self.download(item, drop_after=drop_after.pop(item["id"], None))
            if data is None:  # dropped: reconnect and resume with Range
                data, resumed = self.download(item)
            if resumed:
                result.resumed.append(item["id"])
            sha = hashlib.sha256(data).hexdigest()
            assert sha == item["sha256"], "corrupt download"
            self.sd[f"{item['id']}.{item['format']}"] = SdFile(data, sha)
            self.ack(item["id"], sha).raise_for_status()
            result.delivered.append(item["id"])
        for d in q["deletes"]:
            for name, f in list(self.sd.items()):
                if f.sha256 == d["sha256"] and f.unmodified:
                    del self.sd[name]
                    result.deleted.append(d["sha256"])
        self.last_sync_result = "ok"
        self.post_status().raise_for_status()
        return result
