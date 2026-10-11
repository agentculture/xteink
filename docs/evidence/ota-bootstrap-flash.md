# t16: USB bootstrap flash of the first OTA-capable build

Run 2026-10-11 with the owner present, following the flash protocol: "awake, hands off", by-id port, app-only write, no factory image.

## Before-state (h3)

These greps ran before flashing, all with 0 hits:

- xteink `origin/feat/issue-1`, `xteink/`: no firmware table (`firmware_rollbacks` / `TABLE IF NOT EXISTS firmware`) and no offer field (`"firmware": {` / `/api/device/firmware`).
- fork `feat/issue-1`, `src/`: no daily routine (`DailyRoutine`, `esp_sleep_enable_timer_wakeup`, `last_run`) and no server-offer parsing (`parseStatusResponse`, `FirmwareOffer`).

## Build

- Fork `xteink/ota-daily` @ `f96ca3c6` (the head of agentculture/xteink-firmware#2, CI all green including cppcheck), clean tree.
- Env `xteink_release`. The image is 5,853,664 B, sha256 prefix `7472c1c29457589c`, and carries `xteink-fw 1.6.5+xteink.f96ca3c6`. Footprint guard: ok (10.7% headroom).

## Flash

`esptool v5.3.0 --chip esp32c3 --port <by-id> write-flash 0x10000 firmware.bin` exited 0. It wrote 5,853,664 B (3,981,267 compressed) at `0x10000` in 25.2 s and reported **"Hash of data verified."** It then hard-reset the X3 via RTS. The flash finished at 20:02:09 UTC.

## After

The server's device record for `x3-ori` (id 3, same key, still provisioned):

| Field | Value |
|---|---|
| `firmware_version` | `xteink-fw 1.6.5+xteink.f96ca3c6` |
| `last_run_at` / `last_run_trigger` | `2026-10-11T20:02:16Z` / `power_on` |
| `last_fw_outcome` / `last_content_outcome` | `none` / `ok` |
| `last_sync_result` / `last_error` | `ok` / none |

The Home status line showed "Synced 20:02". The owner later slept and woke the X3, and it went straight to Home with no new run: the routine had already run that local day. This matches the "second start the same day runs 0 routines" half of c25.

## Finding (minor)

The daily routine ran on the boot **right after the flash**, 7 s after esptool finished. The spec says a boot after flashing skips the routine. esptool's RTS reset reaches the firmware as a USB chip reset (`rst:0x15`), which `getWakeupReason` classifies as `Other`, not `AfterFlash`. The impact is a normal sync on a post-flash boot. This is recorded as a follow-up, not fixed in this run.
