# OTA and daily 6am sync

> xteink readers keep themselves current: when the X3 starts for the first time each day, it joins Wi-Fi, installs any new firmware the xteink server offers, then pulls the queued books and articles. If the firmware step can't run unattended, the books still arrive.

## Audience

- The xteink owner reading on an X3 at home, who wants the reader current without a laptop or cable, and the xteink agent (Claude, the mesh resident) as operator: it builds, uploads and offers firmware through the xteink CLI, and the merged fork PR is how the owner hears about it.
  - instruction: Check that the spec's admin flows (CLI firmware noun) and device flows (daily routine) each name this one person as both the reader and the operator.

## Before → After

- Before: Today a firmware update means a USB esptool app-only flash at 0x10000 with the 'awake, hands off' protocol (x3-flash-protocol memory, issue-1 deliveries). Books arrive only when the owner opens Settings > Sync or joins Wi-Fi for another reason (docs/xteink/sync.md 'When it runs'). Nothing happens on its own.
- After: Each day, the first time the owner starts the X3 it brings itself current, installing the offered firmware and pulling everything queued for it, with no cable and no menu. A step that would need a person is postponed and shown on Home, never left hanging. Firmware never leaves the owner's network except over their own tunnel.
  - instruction: Walk the success signals end to end on the real X3, record them in a new `docs/evidence/` file, and confirm each one passed.

## Why it matters

- The reader is meant to work offline on hardware the owner controls. Each USB flash is a bricking risk (a mid-write button press already left the X3 unbootable once), and content that waits for a manual sync goes stale. A local, signed, self-scheduled update keeps both private and hands-off.

## Requirements

- The xteink server stores uploaded firmware images in a separate firmware table and reuses the sha256 blob store; images can't go in items, because items.kind is CHECK-constrained to book/article (xteink/core/store.py:15-58). A schema migration is needed, because the store only runs CREATE TABLE IF NOT EXISTS.
  - honesty: An existing issue-1 library.db opens after the upgrade with its items, devices and queue intact, and gains the firmware table and any new device columns (migration test on a copy of an issue-1 db).
- The device protocol gains an additive firmware offer within v1: the device's POST /api/device/status already reports `firmware_version`, and the server answers with an optional offer (version, size, sha256, url). The image is served under /api/device/ with the existing device-key auth, Range resume and ETag streaming, the same as the book download at `routes_device.py`:223-256.
  - honesty: A firmware build without the change, still speaking protocol v1, syncs unchanged against the new server (the offer field is optional and ignored), and the fake-device test passes for both old and new clients.
- On xteink-provisioned devices, the firmware's OtaUpdater uses the xteink server as its only update source, replacing GitHub releases. It reuses the provisioned LAN and tunnel URLs and the device key from NVS namespace 'xteink' (XteinkConfig), and keeps the existing streaming `esp_ota_begin`/write/end path with its chip-id and board-tag checks (OtaUpdater.cpp:155-259). Before `esp_ota_set_boot_partition` it checks the written bytes against the sha256 in the server's offer.
  - honesty: On a provisioned device, no request goes to api.github.com during an update check (verified by serial log or by blocking GitHub on the LAN), and xteink-check-services.py passes with the GitHub source removed or gated off.
- A new image proves itself before it is kept. The firmware overrides verifyRollbackLater() and calls `esp_ota_mark_app_valid_cancel_rollback` only after a health check passes: boot, display, SD, plus one successful POST /api/device/status to the xteink server within the same routine, retried within a short window. Otherwise the bootloader rolls back to the previous slot.
  - honesty: verifyRollbackLater() is overridden (returns true), and `esp_ota_mark_app_valid_cancel_rollback` is called only after the health check; a forced-fail image rolls back on hardware (S5).
- The routine runs at most once per local day, on the first device start (power-on or wake) after the day turns over at 06:00 in the device's configured timezone (Settings > Clock, default Asia/Jerusalem with DST, src/util/Timezones.cpp:38). A 'last daily run' local date is kept in NVS. Later starts the same day skip straight to Home or the reader.
  - honesty: A unit test against the Asia/Jerusalem POSIX TZ gets the 06:00 day boundary right on both DST transition days in 2026-2027, and a second start on the same local day runs 0 routines.
- The daily run order is: join saved Wi-Fi, check for an offered firmware update and install it, reboot into the new image, then run the existing xteink::sync::run. If the firmware step fails or is skipped (no offer, low battery, download or verify error), the book/article sync still runs in that same wake. The firmware step never blocks content delivery.
  - honesty: In every failure branch of the firmware step (no offer, low battery, download error, sha256 mismatch, needs-human), sync::run still runs in the same start: unit- or host-tested with one case per branch.
- Unattended Wi-Fi and OTA are gated on battery level. The existing sleep-time join requires at least 20% (src/main.cpp:336), and an OTA install needs a higher floor. A gated-off run is recorded in `sync_last` and retried at the next opportunity.
  - honesty: No unattended Wi-Fi join runs below the join floor and no OTA write starts below the OTA floor. Both are named constants with tests, and a skipped run is recorded in `sync_last`.
- Admin surfaces for firmware: a CLI 'firmware' noun (upload/list/offer, dry-run by default with --apply, like device queue/revoke) plus an explain catalog entry; the device card in the web UI shows the offered firmware next to its existing `firmware_version` row; docs/device-protocol.md and docs/api.md are updated. Admin routes go in `routes_admin.py`.
  - honesty: uv run teken cli doctor . --strict passes with the firmware noun and its explain catalog entry, and the CLI firmware verbs are dry-run unless --apply is given.
- The unattended daily run never ends with the device waiting for a human. Any firmware step that can't complete hands-off is deferred and surfaced (on the Home status line and in the server's device record) for the next attended session, after the books have synced.
  - honesty: No code path in the daily routine waits on button input or a confirmation dialog: the routine has a hard wall-clock cap and always ends by going back to sleep or to Home.
- Whether to install is decided by the server's offer, not by isUpdateNewer. Every fork build carries upstream's base 1.6.5 (platformio.ini:6-7), the X3 runs '1.6.5-dev-feat/issue-1-e0aec33f' (docs/evidence/t20-first-sync.md:3), and isUpdateNewer returns false for equal X.Y.Z (OtaUpdater.cpp:104-151). So the device installs when the offer names a build different from the running `CROSSPOINT_VERSION`, older builds included.
  - honesty: Offering a build that differs from the running one only in its -dev suffix and sha gets installed; offering the running build is a no-op.
- The unattended join tries every saved network: last-connected first, then a scan matched against WifiCredentialStore. It doesn't rely on getLastConnectedSsid alone (main.cpp:337), because the X3 holds 2 credentials, and the last one used may be the phone hotspot from a tunnel sync (docs/evidence/t20-first-sync.md). The join has a hard deadline.
  - honesty: With the phone hotspot as the last-connected SSID and only home Wi-Fi in range, the 06:00 run joins home Wi-Fi and syncs.
- The routine never interrupts reading. It runs only at start, before Home or the reader opens. A device left awake across 06:00 just runs it at its next start, with no reboot and no Wi-Fi mid-session, because there is only about 50 KB of heap while reading (platformio.ini:75-81).
  - honesty: Reading across 06:00 causes no reboot, Wi-Fi join or interruption, and the day's run happens at the next start.
- Each daily run reports what happened through additive, optional /api/device/status fields: when the run started, its trigger (power-on or wake), the firmware step outcome (`none`, `installed`, `failed:<code>`, `deferred:<reason>`) and the content outcome. The server keeps the latest per device, and xteink device list --json shows it. Older firmware that omits the fields still works.
  - honesty: A fake-device test posts each outcome and reads it back through device list --json; an old-protocol status without the fields still returns 200.
- The new firmware tolerates an xteink server without the firmware offer, such as an issue-1 server (the offer field is absent), and treats that as 'no update', so content still syncs.
  - honesty: The new firmware against the issue-1 server (origin/feat/issue-1 image) completes a content sync with the firmware step 'none'.
- The server checks an uploaded image before it can be offered: ESP image magic, the chip id at header offset 12 is ESP32-C3, the board tag matches X3, and the size fits a 0x640000 slot (the same checks as OtaUpdater.cpp:184-214). A wrong or garbage upload fails at upload time with a user error (exit 1), not at the device's next start.
  - honesty: Uploading a non-ESP file, an ESP32-S3 image, or an image larger than the slot is rejected by xteink firmware upload with exit 1; a valid X3 image is accepted.
- Settings keeps a manual 'Check for updates' (the existing OtaUpdateActivity, src/activities/settings/SettingsActivity.cpp:410) pointed at the xteink server, so an OTA can be tried with the owner watching before relying on the start routine.
  - honesty: From Settings on the X3, 'Check for updates' shows the server's offered build and installs it, with the same sha256 and health check as the start routine.
- Agent release flow: when a fork PR merges into the fork's integration branch with fork CI green, the xteink agent builds the X3 image with pio from that exact merged commit in a clean worktree, runs xteink firmware upload (admin key via grant inject, as in the issue-1 admin-API pattern), and offers it to every provisioned X3. The upload records the fork commit sha, `CROSSPOINT_VERSION` and the merged PR.
  - honesty: One real run is recorded end to end: fork PR merged, then a build from the merge commit (sha matches), then an upload accepted by the c51 checks, then an offer visible in xteink device list --json, then the X3 installs it at its next first start of the day.
- The merged fork PR is the owner's notification, with no mesh message or other channel. When the offer goes live, the agent comments on that PR with the version, fork commit sha and devices offered (signed as xteink (Claude) by the cicd scripts). If a device later rolls the build back, the agent comments on the same PR.
  - honesty: For the recorded release run, the merged fork PR carries the offer comment naming the same version and sha as the server's offer record, and no message is sent anywhere else.

## Honesty conditions

- All three legs (OTA from the xteink server, the once-a-day start trigger, and books syncing even when firmware can't) are shown on the real X3, not only in unit tests or the fake device.
- privacy-check.sh passes with an OTA leg added to the fake-device flow, and grep finds no outbound HTTP client usage in the firmware code paths of xteink/server or xteink/core.
- partitions.csv is byte-identical to fork feat/issue-1, and the release image built with the changes is under 0x640000 bytes with at least 5% headroom.
- The fork's CI (including xteink-check-services.py and clang-format) is green on the PR, and the fork's commit log for the work has no Co-Authored-By or Claude-Session trailers.
- Every new admin action is reachable from the xteink CLI with --json and a dry-run default, and every device behavior needs zero input on the device.
- The spec's admin flows name the xteink agent as the one who runs the build, upload and offer, and its device flows need zero input from the owner beyond starting the reader.
- The before-state is accurate: on origin/feat/issue-1 and fork feat/issue-1 there is no scheduled sync and no server-hosted OTA (grep for `esp_sleep_enable_timer_wakeup` or a firmware table finds nothing).
- After this ships, a routine firmware update for the X3 needs no USB cable and no esptool.
- Firmware bytes travel only between the owner's server and the device (LAN or the owner's tunnel), and the server makes 0 outbound requests (privacy-check.sh still passes).
- S2 is measured on battery with USB unplugged (isUsbConnected false), timed from the power-button press.
- The sha256 is computed over the exact bytes written to the OTA slot, before `set_boot_partition`; a fixture with 1 flipped byte and a truncated download are both refused in tests.
- The deferral reason is visible on the device without a serial cable (Home status line) and on the server (device record), and is cleared once the human finishes the update.
- Rollback is observed on real hardware, and the device ends up on the previous version without any human action.
- git diff of the fork's feature branch shows no freeink-sdk pointer change.
- This run is recorded as evidence with server-log timestamps, once on USB and once on battery.
- The release procedure refuses (exit non-zero, nothing offered) when the build tree is dirty, the commit isn't on the fork's integration branch, or the version previously rolled back on the target device.

## Success signals

- On battery, powered on after 06:00 with 1 queued book and no run yet that day: the routine runs before Home is usable, and the book is delivered within 120 s of power-on. A second wake the same day triggers 0 additional runs.
  - instruction: Bench run on battery: time from power-on to the ack in the server log; wake a second time and confirm no new status POST with a daily-run marker.
- A corrupted or truncated image (1 flipped byte, or a download cut short) is refused in 100% of attempts: 0 calls to `esp_ota_set_boot_partition`, the device keeps its current `firmware_version`, and the error is reported in `last_error`.
  - instruction: Firmware unit test over the verify function with tampered fixtures, plus one on-device run where the server offers a tampered image.
- When the offered firmware step can't complete unattended (verify fails, low battery, or the server marks the offer as needing a human), the books still sync in the same wake (100% of the queued items that fit) and the firmware is shown as pending on Home and in the device record.
  - instruction: Fake-device server test plus one X3 run with an offer flagged as needing a human.
- An image that boots but fails the post-update health check is rolled back: on the next boot the device reports the previous `firmware_version`, and the bad version is not offered again to that device.
  - instruction: Build a test image whose health check deliberately fails; offer it on the X3 and observe the rollback via serial log (with the user's OK) and the server's device record.
- Started (on USB or battery) for the first time after 06:00, with a new build offered and 1 queued book: the X3 installs, reboots, passes the health check, and delivers the book with 0 touches beyond the start press. The server's device record shows the new `firmware_version` and the item as delivered.

## Scope / boundaries

- The xteink server never fetches firmware from GitHub or anywhere else. Images reach it only by an operator upload, because privacy-check.sh runs the API on an internal:true docker network with no outbound route and requires the fake-device flow to pass offline.
- The partition layout stays as it is: two 0x640000 OTA slots in partitions.csv. The current image is 5,891,200 B, which leaves about 662 KB of headroom per slot, so the OTA and scheduler code must fit inside that headroom.
- The fork's OTA guard stays green: scripts/xteink-check-services.py keeps rejecting the upstream crosspoint release feed in OtaUpdater and setInsecure() in HttpDownloader, TlsTrust and OtaUpdater. Fork commits carry no AI trailers, and the fork's PR titles are conventional commits.
- The freeink-sdk submodule (Free-Ink/freeink-sdk @ 9729236c, .gitmodules) is not modified, and its pointer stays put. The start routine lives entirely in the fork's own code (main.cpp boot path, OtaUpdater, XteinkSync).
- The release flow never flashes over USB and never touches the device directly. It never offers an image that failed the upload checks (c51), a build from an unmerged or locally modified tree, or a build that already rolled back on that device (c28). Fork commits in the flow carry no AI trailers.

## Non-goals

- No automatic article fetching (RSS, web clipping, subscriptions) in this work. 'Books and articles' means whatever is already queued for the device, or kept in mirror mode, through the existing push model.
- Only the X3 is verified. Other Xteink models (X4 and friends) that share the x3-x4 image are not tested or promised here (issue-1 follow-up r7).
- The USB esptool flash and provisioning paths are unchanged. They stay the recovery route, and factory images still wipe NVS.

## Assumptions

- This work builds on issue 1 (xteink PR #4 and fork PR #1, both still open and unmerged). The branch ota/daily-sync is cut from origin/feat/issue-1, and the fork work branches from fork feat/issue-1.
- The X3's I2C RTC (found at boot, docs/evidence/x3-key-mapping-serial.txt:113; 'TLS still verified using the restored RTC clock', t20-first-sync.md:37) keeps time through the GPIO13 battery power-off, so the catch-up check can tell offline whether today's 06:00 has passed.
- The first firmware with server OTA and the start routine reaches the X3 by one USB app-only flash (x3-flash-protocol). The running image (eab86526) has only GitHub OTA, and the fork has no published release that could carry it over the air.
- The trigger for the release flow is the agent's own fork merge (it already merges fork PRs through the cicd skill). There is no webhook or CI push; a merge made by someone else is picked up the next time the agent runs the flow.

## Scope exploration

- `s1` — `xteink/core/store.py (origin/feat/issue-1)`: SQLite schema: the items table has kind CHECK('book','article'). The devices table already has a `firmware_version` column. There is no firmware table and no per-device target version, and the store has no migration path beyond CREATE TABLE IF NOT EXISTS.
  - seeds: `c2`
- `s2` — `docs/device-protocol.md + xteink/server/routes_device.py`: Protocol v1 has the endpoints status, queue, items/{id} and ack. Every status field is optional. `firmware_version` is stored and displayed but nothing acts on it. There is no OTA endpoint. Changes must be additive, or they need a new protocol version (device-protocol.md:4-5). A 426 already means 'firmware update needed'.
  - seeds: `c3`
- `s3` — `.github/scripts/privacy-check.sh + scripts/scan-secrets.py (xteink)`: The privacy gate proves zero egress, and scan-secrets rejects non-localhost URLs in tracked JSON. A server-side OTA source therefore has to be upload-only, and the fake device needs an OTA leg.
  - seeds: `c4`
- `s4` — `xteink-firmware src/network/OtaUpdater.cpp + OtaUpdateActivity`: OTA already exists. Today it checks GitHub releases/latest for agentculture/xteink-firmware (OtaUpdater.cpp:25-32). It parses the release JSON, streams the image over wolfSSL HttpDownloader into `esp_ota_write`, and compares versions with isUpdateNewer, which accepts X.Y.Z only. The UI is under Settings. The source URL is hard-wired.
  - seeds: `c5`
- `s5` — `xteink-firmware partitions.csv + .pio/build/default/firmware.bin`: `ota_0` and `ota_1` are 6,553,600 B each, and otadata is present. The app is 5.89 MB, so about 10% of each slot is free. Changing partitions would need a factory flash, which wipes NVS provisioning (x3-flash-protocol memory).
  - seeds: `c6`
- `s6` — `framework-arduinoespressif32 cores/esp32/esp32-hal-misc.c:286-321 + sdkconfig.defaults:331`: `CONFIG_BOOTLOADER_APP_ROLLBACK_ENABLE`=y, but initArduino marks every booted app valid unless verifyRollbackLater() is overridden, and nothing in src/, lib/ or freeink-sdk overrides it. Today rollback therefore only catches an image that crashes before init. Secure boot and signed apps are off (sdkconfig.defaults:400-402).
  - seeds: `c7`
- `s7` — `xteink-firmware lib/hal/HalClock.cpp, lib/TrustedTime, src/util/Timezones.cpp`: SNTP (HalClock::syncFromNTP, TrustedTime) and the TZ picker exist, and Jerusalem is in the table. TrustedTime.h:6-8 says the C3 keeps time through deep sleep but loses it on power-off, and that there is no battery-backed RTC. An I2C RTC capability is compiled for X3 (BoardConfig.h:302). The xteink/d2-nav-sntp branch is already merged into feat/issue-1.
  - seeds: `c8`
- `s8` — `xteink-firmware src/xteink/XteinkSync.cpp + docs/xteink/sync.md`: sync::run(renderer\*, Callbacks{}, budget) already runs headless (onStationJoined at :831). It does LAN first with a 4 s timeout, then the tunnel, with a 60 s item budget. Results are written to NVS `sync_last` and drawn on Home only when Home repaints. Wi-Fi activities reboot for a fresh heap first, because there is only about 50 KB free while reading and TLS peaks around 39 KB.
  - seeds: `c9`
- `s9` — `xteink-firmware src/main.cpp:325-345 (deliverSleepPluginEvents)`: A headless join of the last-connected SSID already exists: WiFi.begin with a 10 s deadline, gated at 20% battery, and it starts TrustedTime when connected. This is the template for the scheduled join.
  - seeds: `c10`
- `s10` — `xteink CLI/MCP/web (origin/feat/issue-1)`: The CLI nouns are device, library, server, tunnel and mcp. device has list, queue, revoke and overview (device.py:117-141). There are 3 MCP tools: `push_file`, `list_library` and `send_to_device`. DevicesView.tsx:207-210 already shows Firmware when `firmware_version` is set, and api.ts:44 already has it on the Device type. Nothing for schedules or firmware exists anywhere.
  - seeds: `c11`
- `s11` — `xteink-firmware scripts/xteink-check-services.py:99-104 + docs/xteink/CONTRIBUTING.md:14`: The CI guard pins the OTA source away from upstream and bans setInsecure in the OTA/TLS files. CONTRIBUTING says updates come from the fork's releases, never upstream's. That rule and docs/xteink/tls.md:212-228 (the OTA source section) need rewording for a server source.
  - seeds: `c12`
- `s12` — `xteink/core/ingest.py + xteink/mcp/tools.py (origin/feat/issue-1)`: kind='article' is only a label: Markdown/HTML uploads default to it (ingest.py:171). Every item is pushed by the web UI, the CLI or MCP. There is no RSS, URL fetch or scheduled ingest, and there are no server background tasks (only the dual uvicorn asyncio.gather in app.py:188).
  - seeds: `c13`
- `s13` — `gh pr list (xteink #4, fork #1)`: Both issue-1 PRs are OPEN. main holds only the scaffold, so the server, protocol and sync client exist only on the feat/issue-1 branches.
  - seeds: `c14`
- `s14` — `xteink-firmware lib/hal/HalPowerManager.cpp:77-156 + freeink-sdk PowerManager.cpp:60-151`: Sleep on Xteink C3 boards drives GPIO13 low, which cuts power to the battery MOSFET, then runs `esp_deep_sleep_start`. The only armed wake source is the power-button GPIO. `esp_sleep_enable_timer_wakeup` is used nowhere, and HalGPIO::getWakeupReason (HalGPIO.cpp:246-267) has no Timer case. On battery a timer wake is impossible without changing the power-off design; on USB the chip stays in deep sleep.
  - seeds: `q1` (question, resolved)
- `s15` — `xteink-firmware docs/xteink/tls.md + src/network/TlsTrust.h`: The LAN URL may be plain http (TlsTrust.h:15-17); the tunnel requires a pinned CA bundle (XteinkCaBundle.h) plus hostname verification. The GitHub roots in the bundle exist for OTA (tls.md:60). There is no image signing anywhere.
  - seeds: `q2` (question, resolved), `q3` (question, resolved)
- `s16` — `challenge pass / adjacent-systems lens: src/main.cpp:563-597 + lib/hal/HalPowerManager.cpp:77-156`: Three call sites reach the deep sleep: enterDeepSleep, AfterUSBPower and unheld-PowerButton. Only the first runs the sleep-entry hooks. A timer armed in enterDeepSleep alone would miss the plug-in-overnight case.
  - seeds: `c34` (rejected)
- `s17` — `challenge pass / adjacent-systems lens: lib/hal/HalGPIO.cpp:246-267 + src/main.cpp:563-597`: getWakeupReason has no Timer case, so a timer wake falls to Other and the default branch boots the full UI. Without a dedicated path, an unattended wake would leave the device awake on Home and draining.
  - seeds: `c35` (rejected)
- `s18` — `challenge pass / unstated-assumptions lens: src/network/OtaUpdater.cpp:104-151 + platformio.ini:6-7,283`: The frame assumed 'newer' was decidable. In fact dev builds share X.Y.Z with each other, so isUpdateNewer would never offer one of them. Hand-flashed devices run dev builds today.
  - seeds: `c36`
- `s19` — `challenge pass / security lens: decision c18 + c32 (LAN HTTP OTA) + sdkconfig.defaults:400-402`: Image signing alone authenticates the bytes, not the decision to install them. Over plain-HTTP LAN, an attacker can serve any previously signed image (a downgrade replay). Anti-rollback efuses are off, so this has to be enforced in software.
  - seeds: `c37` (rejected)
- `s20` — `challenge pass / adjacent-systems lens: src/activities/settings/SdFirmwareUpdateActivity.cpp + src/network/FirmwareFlasher.cpp`: A second install path, the SD card, exists beside OTA. It validates size and checksum only (SdFirmwareUpdateActivity.cpp:89-97) and isn't covered by c18. Routed to a question for the user.
- `s21` — `challenge pass / failure-mode lens: src/main.cpp:325-345 + src/WifiCredentialStore.cpp:198-210`: The existing headless join (the template for c10) only tries the last SSID. Issue-1 synced over the phone hotspot, so the last SSID is often the wrong one at home in the morning.
  - seeds: `c38`
- `s22` — `challenge pass / lifecycle lens: src/main.cpp:356-391 (enterDeepSleep) + platformio.ini:75-81`: The frame covered 'asleep on USB' and 'off on battery' but not 'awake at 06:00'. The reader heap can't host TLS, so the run has to defer.
  - seeds: `c39`
- `s23` — `challenge pass / security/operations lens: decision c18 + memory issue1-handoff-state (grant secrets)`: c18 named an offline key but not its custody, its rotation or what happens if it is lost. Rotation needs a second compiled-in key slot. Custody routed to a question for the user.
  - seeds: `c40` (rejected)
- `s24` — `challenge pass / recovery lens: c7 + framework esp32-hal-misc.c:286-321`: A health check without network can keep an image whose networking is broken, and that image can never receive the next OTA. That is the worst-case recovery path (USB plus the flash protocol). Routed to a question.
- `s25` — `challenge pass / observability lens: xteink/server/routes_device.py:76-149 (StatusIn) + xteink/core/devices.py:149-164`: Today status carries `last_sync_result` and `last_error` only, so a silent daily-run failure would be invisible on the server. The COALESCE update pattern supports additive optional fields.
  - seeds: `c41`
- `s26` — `challenge pass / migration/compat lens: docs/device-protocol.md (v1, additive) + c3`: c3 covered an old device against a new server, but not a new device against an old server. Firmware and server deploy independently, so both directions matter.
  - seeds: `c42`
- `s27` — `challenge pass / adjacent-systems lens: .gitmodules + freeink-sdk/libs/hardware/PowerManager`: The sleep is entered inside a third-party submodule. Editing it would mean forking a second repo, so the frame keeps the change in the fork's HAL layer.
  - seeds: `c43`
- `s28` — `challenge pass / overlooked-actors lens: src/util/Timezones.cpp + ClockSettingsActivity`: The device already has a user-selectable timezone. Pinning the schedule to Jerusalem would ignore it. Routed to a question.
- `s29` — `challenge pass / lifecycle lens: memory issue1-handoff-state (X3 runs eab86526) + OtaUpdater.cpp:25-32`: Bootstrap: there is a chicken-and-egg step. The device can't OTA into the OTA feature.
  - seeds: `c44`
- `s30` — `challenge pass / concurrency lens: xteink/core/store.py + routes_device.py`: Clean pass. There is one device per key and a single sqlite writer per request. A firmware download beside a book download in the same run is sequential on the device. Residual: two devices fetching the same image at once is plain read concurrency on a content-addressed blob, so there's no new hazard.
- `s31` — `challenge pass / failure-mode lens: OtaUpdater.cpp:155-259 (esp_ota_begin/write/end)`: Clean pass. An interrupted download or power loss mid-write leaves the running slot untouched (begin erases only the inactive slot, and the boot partition switches only after end plus verify). It retries the next day. Residual: no Range resume into an OTA slot, so a flaky link re-downloads the whole 5.9 MB.

## Decisions

- Ordering: firmware first, then books. But if the firmware step would leave the device waiting for a human (e.g. needs a confirmation, a re-provision, or a factory flash, or can't finish unattended), books go first and firmware waits for the human. If the firmware step fails or is skipped, books still sync in the same wake. If battery or time can't cover both, books go first and firmware waits.
- OTA source: on xteink-provisioned devices the xteink server replaces GitHub releases as the only OTA source. Builds are uploaded through a CLI 'firmware' noun, and the operator chooses what each device is offered.
- OTA transport: firmware OTA over the LAN (plain HTTP, checked against the offer's sha256) ships first. OTA over the tunnel stays disabled until a plan task proves a 6 MB+ TLS download on the X3 with no OOM or watchdog reset (closes issue-1 o26/c61). The reason is memory and stability, not security.
- Battery clock: the first plan task bench-tests whether the X3 RTC keeps time through a GPIO13 power-off (power off for 30 min or more, boot offline, compare with the server clock). If it holds, catch-up decides offline from the RTC. If not, catch-up joins Wi-Fi and runs SNTP (about 10 s) on battery wakes until today's run is done.
- The post-update health check requires boot + display + SD + one successful POST /api/device/status to the xteink server within the same routine. If the server is unreachable it retries within a short window, then rolls back.
- The 06:00 trigger follows the device's configured timezone (Settings > Clock), which defaults to Asia/Jerusalem.
- Threat model: accidents, not attackers. The device isn't secret, so there is no image signing, signing key, or anti-downgrade counter. Integrity comes from the sha256 in the server's offer, the ESP image checksum, and the existing chip-id/board-tag checks. Installing an older build is an ordinary operator choice.
- Trigger: the routine runs only when the device starts (power-on or wake). There is no 06:00 timer wake, and the existing sleep/power-off design is unchanged on USB and on battery.
- Firmware publishing is the xteink agent's job, not the owner's. After a fork change merges, the agent builds, uploads and offers the image to the X3 with no approval step. The merged fork PR is how the owner hears about it (c60). The health check + rollback (c7/c47) is the safety net.
- The merged fork PR is the notification. There is no separate mesh message or other channel; offer details and any rollback are reported on that PR.

## Hard questions

- Does the xteink server REPLACE the fork's GitHub-releases OTA source on xteink-provisioned devices, or is it added as a first source with GitHub as fallback? And who decides what a device is offered: a per-device pinned target, the latest uploaded image, or both? (resolved: Server only, replaces GitHub; operator picks per-device offer (c17))
- Integrity: there is no secure boot or app signing (sdkconfig.defaults:400-402), and LAN sync is plain http by design (the c60 trade-off, TlsTrust.h:15-17). A LAN attacker could therefore serve a matching sha256 plus a malicious image. Options: require HTTPS (the tunnel) for firmware only, sign images with a key whose public half is compiled into the firmware, or accept the LAN risk. (resolved: Signed images, offline key, pubkey compiled in (c18))
- On battery, X3 'sleep' is a power-off. HalPowerManager::startDeepSleep drives GPIO13 low, which the code comments call 'the battery power-off' (lib/hal/HalPowerManager.cpp:87-101). The chip and its RTC timer lose power, so nothing can wake the device at 06:00. A timer wake only works while USB keeps the board in charge-sleep. Which model do we take? (a) a scheduled wake only while plugged in; (b) a real ESP deep sleep with a timer on battery, keeping GPIO13 high, which costs standby battery and needs a drain measurement; (c) catch-up: on the first power-on or wake after 06:00, run the daily routine; (d) a combination of (a) and (c). (resolved: User chose plugged-in timer + catch-up (c15))
- What does 'if can't in that order, then books first' mean? (a) if the firmware step fails, still sync books in the same wake (as c9 currently says); (b) when the wake budget, battery or Wi-Fi window is too short for both, do books first and firmware after; or (c) both. (resolved: User: both, and 'can't' means the firmware step would need a human; then books first (c16, c19))

## Open parks

- [unknown_nonblocking] Not examined: Cloudflare tunnel behavior for a 5.9 MB binary at 06:00 (limits, caching). It is moot until tunnel OTA is enabled (c32), and is to be checked in that proof task.
- [unknown_nonblocking] Not examined: battery cost of the daily Wi-Fi join plus OTA write on the X3 (mAh per run). The battery floors in c10 are guesses until it is measured.
- [unknown_nonblocking] Which fork branch counts as the integration branch for releases? Today the work lives on fork feat/issue-1 (PR agentculture/xteink-firmware#1 is open). After that merges it is probably the fork's default branch; to be settled in /spec-to-plan.

## Resolved vagueness

- [unknown_blocking] Real deep-sleep battery drain on the X3 with GPIO13 held high (board quiescent current) is unmeasured, so option (b) of q1 needs a bench measurement over hours before it can be chosen. — resolved: Moot: battery timer wake not chosen (c15)
- [unknown_nonblocking] Whether the X3's I2C RTC (BoardConfig.h:302; PCF8563 or DS3231) has an alarm/INT line that could power the board on or wake it is a hardware schematic question that the code does not answer. — resolved: Moot: no timer wake (c50)
- [unknown_blocking] A TLS download of 5 MB or more on the ESP32-C3 has never been run on hardware (issue-1 open items o26/c61). The firmware image is 5.9 MB, so an over-the-tunnel OTA hits this directly. — resolved: LAN OTA first; tunnel OTA gated on a hardware TLS proof task (c32)
- [unknown_nonblocking] RC slow-clock drift across a ~24 h deep sleep is unquantified (the docs have no figure), so the wake may land minutes off 06:00 unless the delay is re-derived or corrected at each wake. — resolved: Moot: no timer wake, so no 24 h sleep drift (c50)
- [follow_up] Over-the-air firmware currently comes from GitHub releases whose asset is named `crosspoint-<tag>-x3-x4.bin` (release.yml:140). How does a build reach the server: a manual upload via the CLI, or a later CI push? Manual upload is assumed for now. — resolved: Manual CLI upload (c54)
- [unknown_blocking] Does the X3 RTC keep time through a battery power-off? If not, catch-up must join Wi-Fi and SNTP on each battery wake until today's run is done (one join of about 10 s per wake), or it treats 'floor date < today' as unknown. — resolved: Bench-test the RTC as the first task; SNTP-join fallback (c33)
