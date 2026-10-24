# Xteink device protocol v1

This is the contract between the xteink server and the Xteink reader firmware.
Keep it small. A change that breaks an existing v1 device needs a new protocol
version, not an edit to this one.

Implementation: `xteink/server/routes_device.py`. Reference client used by the
test suite: `tests/server/fake_device.py`.

## Transport

The device talks to the **device app** only (default port 8781 on the LAN, or
the Cloudflare Tunnel hostname). Every path is under `/api/device/`. Download
`url` values in responses are paths relative to the server root, so the same
response works over the LAN and through the tunnel.

Every request carries two headers:

```http
Authorization: Bearer xtd_EXAMPLEDEVICEKEY
X-Xteink-Protocol: 1
```

- **Device key.** Each device has its own `xtd_` key, issued when it is
  registered (`POST /api/devices` on the main app) and shown once. A missing,
  unknown, rotated-out or revoked key gets `401`. Auth is checked before the
  protocol version.
- **Protocol version.** A missing or unsupported `X-Xteink-Protocol` gets `426`
  with `Upgrade: xteink-device/1` and a body naming the supported versions:

```json
{"detail": {"message": "unsupported device protocol (X-Xteink-Protocol '2'); this server speaks X-Xteink-Protocol: 1", "supported": ["1"]}}
```

## Sync flow

1. `POST /api/device/status`: report free space, firmware, last error and inventory.
   If the response carries a `firmware` offer, the device may fetch it from
   `GET /api/device/firmware/<id>` (see [OTA](#get-apidevicefirmwareid)).
2. `GET /api/device/queue`: get items to fetch, items skipped, and deletes.
3. For each item, `GET` its `url`. If the connection drops, resume with `Range`.
4. Hash the file on-device. `POST /api/device/ack` with that sha256.
5. Mirror devices only: remove the files listed in `deletes`.
6. `POST /api/device/status` again with `last_sync_result` (and `last_error`).

The device must send step 1 at the start of every sync. The queue's free-space
and delete decisions use the most recent report.

## Endpoints

### POST /api/device/status

```json
{
  "free_sd_bytes": 734003200,
  "firmware_version": "xteink-fw 0.1.0",
  "last_error": null,
  "last_sync_result": "ok",
  "inventory": [
    {"sha256": "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08", "unmodified": true}
  ]
}
```

All fields are optional. `last_sync_result` and `last_error` describe this report
and replace the previous ones; `free_sd_bytes` and `firmware_version` are kept
from an earlier report when a report leaves them out. The server records
`last_seen`. `inventory` lists **only files the server delivered**. For
each, the device re-hashes the file and sets `unmodified` to whether it still
matches the delivered sha256. Files the user sideloaded are never in the
inventory, so the server can never ask for them to be deleted. If `inventory` is
omitted, the previous inventory is kept.

The server keeps inventories in memory, per process. After a server restart no
deletes are sent until the device's next status report.

Response `200`: `{"protocol": "1", "device": {...}}`, the device's stored status.

#### Daily-run and OTA fields (additive v1)

A device may also send these optional fields. Old clients that send none of them
keep working unchanged.

```json
{
  "run_started_at": "2026-10-11T06:00:03Z",
  "run_trigger": "power_on",
  "fw_outcome": "deferred:low_battery",
  "content_outcome": "ok",
  "rolled_back_version": "xteink-fw 0.2.0"
}
```

| Field | Values | Stored as |
|-------|--------|-----------|
| `run_started_at` | When the current daily run started, as a string (ISO 8601 UTC recommended), max 64 chars | `last_run_at` |
| `run_trigger` | `power_on`, `wake` or `manual` | `last_run_trigger` |
| `fw_outcome` | `none`, `installed`, `failed:<code>` or `deferred:<reason>`. `<code>`/`<reason>` is free text that must not start with whitespace. Max 200 chars | `last_fw_outcome` |
| `content_outcome` | Free text summary of the content sync (for example `ok`, `partial`), max 200 chars | `last_content_outcome` |
| `rolled_back_version` | The firmware version string the device just rolled back from, max 200 chars | a rollback record (see below) |

Any other `run_trigger`, or an `fw_outcome` outside that shape, gets `422`.
The four run fields describe the most recent run: like `firmware_version`, a
report that leaves one out keeps the stored value, so a run's first and last
status reports can each send only what they know.

`rolled_back_version` is matched against uploaded firmware by version string.
If several uploads share that version, the device's current offer wins,
otherwise the newest upload. The server records that this device rolled that
image back, withdraws it if it is the current offer, and never offers it to
this device again. A version that matches no upload records nothing; the
request still succeeds with `200`.

#### Firmware offer in the response (additive v1)

When the operator has offered an image to this device **and** its version
differs from the device's `firmware_version` (from this report, or the stored
one if this report leaves it out), the response gains a `firmware` object:

```json
{
  "protocol": "1",
  "device": {"...": "..."},
  "firmware": {
    "id": 7,
    "version": "xteink-fw 0.2.0",
    "size": 1572864,
    "sha256": "...",
    "url": "/api/device/firmware/7"
  }
}
```

The key is absent when there is no offer, when the device already runs that
version, or once the device has reported rolling it back. An offer the device
reports running is fulfilled and is withdrawn, so it does not come back as a
downgrade when the device later runs another build. Old clients ignore it. The `url` is relative to the server root, like item URLs.

### GET /api/device/queue

Response `200`:

```json
{
  "protocol": "1",
  "items": [
    {"id": 42, "title": "Dune", "size": 812345, "sha256": "...", "format": "epub", "kind": "book", "url": "/api/device/items/42"}
  ],
  "skipped": [{"id": 43, "reason": "sd_full"}],
  "deletes": [{"sha256": "..."}]
}
```

- `items`: entries queued (not yet acked) for this device, in queue order.
  Each entry has `kind`, one of `book`, `article`, `transcript` or `newspaper`.
  An absent or unknown `kind` is treated as `book`. Firmware that knows the
  kinds files each item in its folder: articles in `/xteink/articles/`,
  transcripts in `/xteink/transcripts/`, newspapers in `/xteink/newspapers/`,
  and books in `/xteink/`. Files already delivered are not moved. Older
  firmware ignores the field.
- `skipped`: queued items that do not fit. The budget is the last reported
  `free_sd_bytes` minus a 1 MiB safety margin. Items are taken in order and each
  included item uses up budget. An item larger than what is left is skipped
  with `reason: "sd_full"` and stays queued. If free space was never reported,
  nothing is skipped.
- `deletes`: always empty for non-mirror devices. For a mirror-mode device it
  lists every inventory sha256 that the device reported as `unmodified: true`
  and that is no longer in the library. Modified (annotated) copies are never
  deleted. The device deletes a file only if its current hash still equals the
  listed sha256.

### GET /api/device/items/`id`

Returns the item's bytes, with `Accept-Ranges: bytes` and `ETag: "<sha256>"`.
Only items queued for or delivered to **this** device are served. Any other id
gets `404`.

To resume after a dropped connection, send a single byte range:

```http
GET /api/device/items/42
Range: bytes=300-
```

The response is `206` with `Content-Range: bytes 300-812344/812345`. Accepted
forms are `bytes=a-b`, `bytes=a-` and `bytes=-n`. An end past the file is
clamped. A start at or past the end, a reversed range, a malformed value or a
multi-range request gets `416` with `Content-Range: bytes */<size>`.

### GET /api/device/firmware/`id`

Additive v1. Returns the offered firmware image's bytes
(`application/octet-stream`) with `Accept-Ranges: bytes` and
`ETag: "<sha256>"`. Same device-key auth and protocol header as every other
route. Only the image currently offered to **this** device is served. Any
other id, including another device's offer, a withdrawn offer or an unknown id,
gets `404`.

Range handling is exactly as for items: resume a dropped download with
`Range: bytes=<received>-` and get `206`; an unsatisfiable or unsupported range
gets `416` with `Content-Range: bytes */<size>`. The device must check the
whole image against the offer's `sha256` (and `size`) before installing it.

### POST /api/device/ack

```json
{"item_id": 42, "sha256": "..."}
```

The sha256 must be the hash of the bytes the device stored. If it matches, the
entry becomes `delivered`. Response `200`:
`{"protocol": "1", "id": 42, "state": "delivered", "delivered_at": "..."}`.
Acking an already-delivered item again is harmless.

## Errors

Error bodies are JSON with a `detail` field.

| Status | Meaning | Device action |
|--------|---------|---------------|
| `401` | Missing, unknown, rotated-out or revoked device key | Stop syncing and show "re-pair device" |
| `404` | Item not queued for this device, or no longer in the library; or firmware not offered to this device | Drop it and re-fetch the queue (or re-post status for the current offer) |
| `409` | Ack sha256 does not match the item | Delete the copy and download it again |
| `416` | Unsatisfiable or unsupported `Range` | Discard partial bytes and download from 0 |
| `422` | Malformed request body (bad field, non-hex sha256, negative size, unknown `run_trigger`, bad `fw_outcome`) | Firmware bug: report in `last_error` |
| `426` | Missing or unsupported `X-Xteink-Protocol` | Firmware update needed |

## Changelog

- **v1**: initial protocol (status with inventory, queue with `sd_full` and
  mirror deletes, ranged download, sha256 ack).
- **v1, additive (OTA + daily run)**: still `X-Xteink-Protocol: 1`; nothing an
  existing v1 device sends or reads changed. `POST /api/device/status` accepts
  the optional `run_started_at`, `run_trigger`, `fw_outcome`, `content_outcome`
  and `rolled_back_version` fields and may return a `"firmware"` offer object
  (`id`, `version`, `size`, `sha256`, `url`). New route
  `GET /api/device/firmware/<id>` serves the device's own offered image with
  `Range` and `ETag`.
- **v1, additive (kind)**: still `X-Xteink-Protocol: 1`; nothing an existing v1
  device sends or reads changed. Each `items` entry of `GET /api/device/queue`
  gains `kind` (`book`, `article`, `transcript` or `newspaper`). An absent or
  unknown kind is read as `book`, and older firmware ignores the field.
