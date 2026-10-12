"""A fake Xteink reader that speaks device protocol v1 (docs/device-protocol.md).

It holds an in-memory "SD card", reports free space, can drop a download
mid-stream and resume it with an HTTP ``Range`` request, and acks by sha256.

By default it is an **old client**: it sends exactly the original v1 status body and
ignores any firmware offer. ``new_client=True`` opts into the additive v1 fields: the
daily-run status fields, and fetching (with ``Range`` resume) a firmware offer that the
status response carries.
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
    firmware_offer: dict | None = None  # the status response's 'firmware' object
    firmware_resumed: bool = False


class FakeDevice:
    def __init__(
        self,
        client,
        key: str,
        *,
        sd_capacity: int = 10_000_000,
        firmware_version: str = "xteink-fw 0.1.0",
        protocol: str = PROTOCOL,
        new_client: bool = False,
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
        # New-client (additive v1) state; never sent by an old client.
        self.new_client = new_client
        self.run_started_at: str | None = None
        self.run_trigger: str | None = None
        self.fw_outcome: str | None = None
        self.content_outcome: str | None = None
        self.rolled_back_version: str | None = None
        self.firmware_image: bytes | None = None  # last fully downloaded, verified image

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

    def status_body(self) -> dict:
        body = {
            "free_sd_bytes": self.free_sd_bytes,
            "firmware_version": self.firmware_version,
            "last_error": self.last_error,
            "last_sync_result": self.last_sync_result,
            "inventory": self.inventory(),
        }
        if self.new_client:
            for name in (
                "run_started_at",
                "run_trigger",
                "fw_outcome",
                "content_outcome",
                "rolled_back_version",
            ):
                value = getattr(self, name)
                if value is not None:
                    body[name] = value
        return body

    def post_status(self):
        return self.client.post(
            "/api/device/status", headers=self.headers(), json=self.status_body()
        )

    def get_queue(self):
        return self.client.get("/api/device/queue", headers=self.headers())

    def download(self, item: dict, *, drop_after: int | None = None) -> tuple[bytes | None, bool]:
        """Fetch ``item['url']``, resuming from any partial bytes already held.

        ``drop_after`` simulates the connection dying after that many body bytes:
        the partial bytes are kept and ``(None, False)`` is returned.
        Returns ``(data, resumed)`` on completion.
        """
        return self._fetch(item["id"], item["url"], item["size"], drop_after)

    def download_firmware(
        self, offer: dict, *, drop_after: int | None = None
    ) -> tuple[bytes | None, bool]:
        """Fetch a firmware offer's ``url`` like :meth:`download` (Range resume)."""
        return self._fetch(("fw", offer["id"]), offer["url"], offer["size"], drop_after)

    def _fetch(self, key, url: str, size: int, drop_after: int | None):
        buf = self.partial.setdefault(key, bytearray())
        resumed = len(buf) > 0
        headers = self.headers()
        if resumed:
            headers["Range"] = f"bytes={len(buf)}-"
        with self.client.stream("GET", url, headers=headers) as r:
            expected = 206 if resumed else 200
            if r.status_code != expected:
                raise AssertionError(f"download {url}: {r.status_code} {r.read()!r}")
            if resumed:
                assert r.headers["content-range"] == f"bytes {len(buf)}-{size - 1}/{size}"
            for chunk in r.iter_bytes(chunk_size=64):
                if drop_after is not None and len(buf) + len(chunk) >= drop_after:
                    buf.extend(chunk[: drop_after - len(buf)])
                    return None, False  # connection dropped mid-stream
                buf.extend(chunk)
        data = bytes(self.partial.pop(key))
        return data, resumed

    def ack(self, item_id: int, sha256: str):
        return self.client.post(
            "/api/device/ack", headers=self.headers(), json={"item_id": item_id, "sha256": sha256}
        )

    # -- full flow ----------------------------------------------------------

    def sync(
        self,
        *,
        drop_after: dict[int, int] | None = None,
        firmware_drop_after: int | None = None,
    ) -> SyncResult:
        """status -> [new client: firmware offer] -> queue -> download (resume on drop)
        -> sha256 ack -> deletes -> status."""
        drop_after = dict(drop_after or {})
        result = SyncResult()
        r = self.post_status()
        r.raise_for_status()
        offer = r.json().get("firmware") if self.new_client else None
        if offer is not None:
            result.firmware_offer = offer
            image, resumed = self.download_firmware(offer, drop_after=firmware_drop_after)
            if image is None:  # dropped: reconnect and resume with Range
                image, resumed = self.download_firmware(offer)
            result.firmware_resumed = resumed
            assert hashlib.sha256(image).hexdigest() == offer["sha256"], "corrupt firmware"
            assert len(image) == offer["size"]
            self.firmware_image = image
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
