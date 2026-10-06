"""Plain dataclasses returned by the services."""

from __future__ import annotations

from dataclasses import dataclass

KINDS = ("book", "article")


@dataclass(frozen=True)
class Item:
    id: int
    sha256: str
    kind: str
    title: str
    author: str
    format: str
    size: int
    created_at: str


@dataclass(frozen=True)
class AddResult:
    item: Item
    created: bool  # False when an identical sha256 already existed


@dataclass(frozen=True)
class Device:
    id: int
    name: str
    key_id: str
    mirror: bool
    created_at: str
    revoked_at: str | None
    last_seen: str | None
    last_sync_result: str | None
    free_sd_bytes: int | None
    firmware_version: str | None
    last_error: str | None


@dataclass(frozen=True)
class QueueEntry:
    """One item queued for a device (sync protocol v1 fields + state)."""

    id: int
    device_id: int
    item_id: int
    title: str
    size: int
    sha256: str
    state: str  # 'queued' | 'delivered'
    queued_at: str
    delivered_at: str | None


@dataclass(frozen=True)
class ApiKey:
    id: int
    name: str
    key_id: str
    created_at: str
    revoked_at: str | None
    last_used: str | None
