# t2: 6 MB download test, first attempt (found an SD bug)

Run 2026-10-11 with the owner present. The X3 was on USB, running firmware `1.6.5-dev-feat/issue-1-eab86526` as device id 3. A padded test EPUB (6,498,206 B of random filler, sha256 `ebe80f69…`, never committed) was queued as library item 6. The serial log was read-only with the owner's OK. The raw log stays in the session scratchpad because it contains a home network identifier. Opening the port reset the X3 (`rst:0x15 USB_UART_CHIP_RESET`), even with DTR/RTS held low.

## What ran

Both syncs auto-joined the saved home network, so they used the LAN origin (`http://192.168.1.157:8781`), not the tunnel. **The tunnel/TLS question was not exercised.**

| Run | Bytes written before failure | Error | Last e-ink refresh done → failure |
|---|---|---|---|
| 1 | 1,398,616 / 6,498,206 | `ESD` (status 200) | 12,133 ms → 12,527 ms |
| 2 | 989,428 / 6,498,206 | `ESD` (status 200) | 16,356 ms → 17,200 ms |

Free heap stayed around 84-86 KB, and the SD card reported 15.7 GB free. A 3,201 B item in the same sync delivered fine. `ESD` comes from `file.write()` returning short mid-stream (`src/xteink/XteinkSync.cpp:376`).

## Verdict

- **Tunnel OTA viability: not tested.** Deferred to the owner's next sync away from home, with the server log as evidence (deviation d7).
- **New bug:** on the current firmware, downloads over about 1 MB fail with an SD write error. The failure point varies, but each failure came 0.4-0.85 s after a progress-bar e-ink refresh. The working hypothesis is display/SD contention; it is unproven. A fix is tracked as d7-fix.
- Cleanup: item 6 was removed from the library, and device 3's queue is empty.
