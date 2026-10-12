# t17: on-device validation (in progress)

The X3 is `x3-ori`, device id 3. The live server runs `ota/daily-sync` @ `f17c62d` (d10). Serial logs were read-only with the owner's OK; the raw logs stay in the session scratchpad.

## Release flow and PR notification (t15, c56/c57)

Fork PR agentculture/xteink-firmware#2 was merged into `feat/issue-1` as `2500570d` (owner's gate). Then `scripts/firmware-release.py release 2` ran, exit 0. It built `xteink_release` from the merge commit (`1.6.5+xteink.2500570d`, 5,853,664 B), uploaded it as firmware #1, offered it to `[3]`, and commented on PR #2: "Firmware released over the air", with the version, fork commit and devices offered, signed `- xteink (Claude)`.

## (f) Settings > Check for updates: PASS

The log shows: offer `install (1.6.5+xteink.2500570d, running 1.6.5+xteink.f96ca3c6)` → `Installing … 5853664 B` → `Update completed` (about 32 s over LAN) → reboot (`rst:0xc`) → `Health check of xteink-fw 1.6.5+xteink.2500570d: valid (ok, 1 attempts, 1520 ms)` → next offer `none (-, running 1.6.5+xteink.2500570d)`. The server recorded `firmware_version: xteink-fw 1.6.5+xteink.2500570d`. The offer was not re-sent after the install, which confirms the prefix fix `f17c62d`.

## Large book, d7 fix: PASS

The same 6,498,206 B test EPUB that failed twice with `ESD` on the issue-1 firmware (`ota-tls-6mb.md`) was delivered over LAN in about 16 s: `Sync done: OK, 1 new … 0 failed`. The log has **0** `SD write … failed` or retry lines, and the server shows the item as `delivered`. That zero-retry result supports the card-latency hypothesis: aligned 4 KB writes removed the stalls. The test item was removed from the library afterwards.

## (c) Corrupted image: PASS

A copy of a valid build with one byte flipped at offset 3,000,000 was uploaded as firmware #2, `1.6.5+xteink.t17corrupt`. The server accepted it (the header is valid) and offered it. The device downloaded the whole image; the sha256 matched, because the server hashed the corrupted bytes. Then `esp_image: Checksum failed` → `New image failed verification` → `esp_ota_end failed: ESP_ERR_OTA_VALIDATE_FAILED` → `Firmware install failed: EFLASH`, with no reboot, and the device stayed on `…2500570d`. The test record remains in the live firmware table, and the device's offer was switched back.

## (e) Rollback: NOT PROVEN on device (open)

A valid older build (`1.6.5+xteink.f96ca3c6`, firmware #3) was offered and installed. The `api` container and the device tunnel connector were stopped as `Update completed` appeared. The new image's health check got no answer on LAN, but **Cloudflare's edge answered HTTP 530** for the tunnel host. Under d8 ("any HTTP answer = healthy") the image was kept: `valid (ok, 1 attempts, 5445 ms)`. Server downtime was about 45 s.

This is consistent with d8's intent (the image booted and completed TLS to the internet), but it means stopping the server cannot trigger a rollback. The owner chose to skip a forced-failure test for now. Rollback is still evidenced only by bootloader config (`ota-bootloader-rollback-check.md`) and host tests.

## (a) First start after 06:00 on USB: install and sync PASS, outcome report FAIL (fixed in fork PR #3)

The owner woke the X3 at 07:02 Israel time on 2026-10-12, on USB. Attaching the serial logger reset the device once at boot (`rst:0x15`), before Wi-Fi came up.

- **Boot 1:** at 4.2 s the device logged offer `install (1.6.5+xteink.2500570d, running 1.6.5+xteink.f96ca3c6)`. It logged `Installing … 5853664 B` at 4.7 s and `Update completed` at 35.4 s (31 s over LAN), then `Firmware installed; rebooting into it`. The splash screen stayed up for the whole install.
- **Boot 2** (`rst:0xc`): at 4.1 s the device logged `Health check of xteink-fw 1.6.5+xteink.2500570d: valid (ok, 1 attempts, 1905 ms)`. The routine reused the health check's offer and synced (`Sync done: OK, 1 new … 0 failed`). It then logged `Daily routine: ran (clock system, fw none, content ok, 3967 ms)`.
- **Server:** `firmware_version: xteink-fw 1.6.5+xteink.2500570d`, `last_run_at` 04:02:45Z. It also recorded **`last_fw_outcome: none`**, where it should have been `installed`.

**Cause (lapse l15).** The server leaves out the offer once the device runs the offered build, so boot 2 saw decision `None`. The routine reported `installed` only on `Current`. The device tests modelled the server as still offering the running build, and no test paired the two sides. Approved fix (d11): the routine reports `installed` when this boot's post-update health check verified the image. This is agentculture/xteink-firmware#3. The on-device proof is the next update after that PR merges.

`clock system` does not answer t1's question. On USB the chip never loses power, so the system clock simply ran on.

## Still to run

- **(a′)** Fork PR #3 was squash-merged as `c6e8b2cf`. `firmware-release.py release 3` uploaded it as firmware #4 and offered it to `[3]`. At 05:09:53Z the owner ran Settings → Check for updates. The server first saw the X3 on `…2500570d`, then at 05:10:43Z on `xteink-fw 1.6.5+xteink.c6e8b2cf`. That second report is the new image's post-update health-check POST. `last_fw_outcome` stays `none` today, because today's daily run has already happened and the manual path never reports a run outcome. **Still open:** at the first start after 06:00 on 2026-10-13, the daily run should read the `fw_verified` marker written by this health check and report `last_fw_outcome: installed`. This exercises the marker surviving reboots and the day boundary.
- **(b)** A battery start, timed from the power press (120 s target, lapse l2). This also answers t1's question (whether the RTC holds through power-off), from the routine's `clock rtc/system/sntp` log field.
- **(d)** and **t2**: a tunnel-only offer and tunnel TLS, the next time the owner syncs away from home.

## Other observations

- Once-a-day gate: every later boot today logged `Daily routine: not-due (clock system …)`, so later starts on the same local day ran 0 routines.
- The routine also ran on the boot right after the USB bootstrap flash (l13; esptool's RTS reset reads as `Other`).
- After the failed rollback test, the server's stored `firmware_version` was stale (the post-install report only reached Cloudflare's 530). It self-corrects, because every status POST carries the device's real version and the offer is compared against it.
