"""Plain dataclasses returned by the services."""

from __future__ import annotations

from dataclasses import dataclass

KINDS = ("book", "article", "transcript", "newspaper")


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
    # Schema v2 (OTA + daily run). Defaults keep the dataclass constructible without them.
    offered_firmware_id: int | None = None
    last_run_at: str | None = None
    last_run_trigger: str | None = None
    last_fw_outcome: str | None = None
    last_content_outcome: str | None = None


@dataclass(frozen=True)
class QueueEntry:
    """One item queued for a device (sync protocol v1 fields + state)."""

    id: int
    device_id: int
    item_id: int
    title: str
    size: int
    sha256: str
    format: str
    kind: str
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


@dataclass(frozen=True)
class Firmware:
    """An uploaded device image; its bytes live in the sha256 blob store."""

    id: int
    version: str
    sha256: str
    size: int
    board: str
    fork_commit: str | None
    source_pr: str | None
    created_at: str


@dataclass(frozen=True)
class AddFirmwareResult:
    firmware: Firmware
    created: bool  # False when an image with the same sha256 already existed


@dataclass(frozen=True)
class OfferAllResult:
    """Outcome of offering one image to every provisioned device."""

    firmware: Firmware
    offered: tuple[int, ...]  # device ids now offered this image
    skipped_revoked: tuple[int, ...]
    skipped_rolled_back: tuple[int, ...]
