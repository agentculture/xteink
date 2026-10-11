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

## Still to run

- **(a)** First start after 06:00 on USB: the latest build (`…2500570d`, firmware #1) is offered to the X3, which currently runs `…f96ca3c6`. The routine should install it, pass the health check and sync.
- **(b)** A battery start, timed from the power press (120 s target, lapse l2). This also answers t1's question (whether the RTC holds through power-off), from the routine's `clock rtc/system/sntp` log field.
- **(d)** and **t2**: a tunnel-only offer and tunnel TLS, the next time the owner syncs away from home.

## Other observations

- Once-a-day gate: every later boot today logged `Daily routine: not-due (clock system …)`, so later starts on the same local day ran 0 routines.
- The routine also ran on the boot right after the USB bootstrap flash (l13; esptool's RTS reset reads as `Other`).
- After the failed rollback test, the server's stored `firmware_version` was stale (the post-install report only reached Cloudflare's 530). It self-corrects, because every status POST carries the device's real version and the offer is compared against it.
