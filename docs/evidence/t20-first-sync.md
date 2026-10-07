# t20 evidence: first device sync (hotspot + tunnel)

Run 2026-10-06, X3 `68:c6:3a:3b:c2:4c`, firmware `1.6.5-dev-feat/issue-1-e0aec33f`, device id 2 (`x3-ori`, key id `a0f17e7a`).

## Push (MCP)

`push_file` on the production MCP server (`http://127.0.0.1:8782/mcp/`) with a Markdown article, `device: x3-ori`: converted to EPUB (7,223 B, sha256 `039bf8193ed7af8537c05d1056008033ff9b69e66d6de1f50ac04fc1ed415b60`), queued 20:36:53Z, call took 0.58 s.

## Sync ("Sync books now")

```text
[1544] [DBG] [WCS] Loaded 2 WiFi credentials from file
[4446] [DBG] [WIFI] Attempting saved network: iPhone (5)
[8664] [DBG] [WIFI] Connected BSSID: <redacted>, channel: 6, RSSI: -38 dBm
[8665] [INF] [CLK] Starting NTP sync...
[13665] [ERR] [CLK] NTP sync timed out
[14172] [INF] [XSYNC] Sync start (key id a0f17e7a, heap 87484, max block 77812)
[25228] [INF] [XSYNC] No answer from http://192.168.1.157:8781
[25232] [ERR] [TLS] SNTP sync failed; certificate date checks use the restored clock
[28899] [INF] [XSYNC] Using https://xteink.culture.dev
[28899] [ERR] [TLS] SNTP sync failed; certificate date checks use the restored clock
[29118] [INF] [XSYNC] Queue: 1 items, 0 skipped, 0 deletes, 0 dropped
[31730] [ERR] [TLS] SNTP sync failed; certificate date checks use the restored clock
[35388] [DBG] [BookCache] Done checking metadata cache for: /xteink/<article>.epub
[39289] [ERR] [TLS] SNTP sync failed; certificate date checks use the restored clock
[51119] [ERR] [TLS] SNTP sync failed; certificate date checks use the restored clock
[51429] [INF] [XSYNC] Sync done: OK, 1 new, 0 deleted, 0 skipped, 0 failed
```

- Server: `delivered_at` 2026-10-06T20:38:34Z (device ack, sha256 verified).
- Wi-Fi join (8.7 s) to sync done (51.4 s): 42.8 s, within the 60 s budget of c48.
- Path: hotspot `iPhone (5)` -> LAN URL unreachable (no route) -> `https://xteink.culture.dev` with pinned-root TLS.
- Heap at sync start: 87,484 B free, 77,812 B largest block.

## Findings

- SNTP timed out on the hotspot and is retried on every HTTPS connection (6 failures), adding delay per request; TLS still verified using the restored RTC clock.
- LAN probe took ~11 s to fail against a 4 s connect-timeout setting.
- Not yet checked: reading >= 10 pages with Wi-Fi off; home-LAN sync path; button/zoom/menu checklist.
