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

### GET /api/device/queue

Response `200`:

```json
{
  "protocol": "1",
  "items": [
    {"id": 42, "title": "Dune", "size": 812345, "sha256": "...", "format": "epub", "url": "/api/device/items/42"}
  ],
  "skipped": [{"id": 43, "reason": "sd_full"}],
  "deletes": [{"sha256": "..."}]
}
```

- `items`: entries queued (not yet acked) for this device, in queue order.
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
| `404` | Item not queued for this device, or no longer in the library | Drop it and re-fetch the queue |
| `409` | Ack sha256 does not match the item | Delete the copy and download it again |
| `416` | Unsatisfiable or unsupported `Range` | Discard partial bytes and download from 0 |
| `422` | Malformed request body (bad field, non-hex sha256, negative size) | Firmware bug: report in `last_error` |
| `426` | Missing or unsupported `X-Xteink-Protocol` | Firmware update needed |

## Changelog

- **v1**: initial protocol (status with inventory, queue with `sd_full` and
  mirror deletes, ranged download, sha256 ack).
