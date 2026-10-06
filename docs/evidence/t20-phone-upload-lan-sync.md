# t20 evidence: phone upload via SSO, delivered over the home LAN

Run 2026-10-07 (UTC 2026-10-06 21:46-21:49), X3 `x3-ori` device id 3 (key id `2ee4d87f`), firmware `1.6.5-dev-feat/issue-1-fd17732e`.

## Upload from the phone (ebooks.culture.dev, Cloudflare SSO only)

```text
INFO:     172.28.0.3:39178 - "POST /api/library HTTP/1.1" 201 Created
INFO:     172.28.0.3:36062 - "POST /api/devices/3/queue HTTP/1.1" 201 Created
```

Item 2: Markdown article converted to EPUB by the image pandoc 3.12 (7,629 B, sha256 `f4eba8005d8f3f0e1154abac278dde244b10428d8ac5329447c5e1cc3f5bda6c`).

## Device sync (serial log)

```text
[1548] [DBG] [WCS] Loaded 2 WiFi credentials from file
[1549] [DBG] [WIFI] Attempting saved network: iPhone (5)
[8551] [DBG] [WIFI] Saved network failed: iPhone (5)
[11253] [DBG] [WIFI] Attempting saved network: <extender SSID>
[18266] [DBG] [WIFI] Saved network failed: <extender SSID>
[41761] [DBG] [WiFi] Using saved password for <extender SSID>, length: <redacted>
[50069] [DBG] [WIFI] Connected BSSID: <redacted>, channel: 11, RSSI: -49 dBm
[54370] [INF] [CLK] RTC set to 2026-10-06 21:48:53 UTC
[54911] [INF] [XSYNC] Sync start (key id 2ee4d87f, heap 86764, max block 77812)
[54927] [INF] [XSYNC] Inventory: 1 files hashed in 16 ms
[61916] [INF] [XSYNC] Free space query: 6988 ms
[62066] [INF] [XSYNC] Using http://192.168.1.157:8781 (146 ms)
[62081] [INF] [XSYNC] Queue: 1 items, 0 skipped, 0 deletes, 0 dropped
[62546] [DBG] [BookCache] Done checking metadata cache for: /xteink/<article>.epub
[62640] [INF] [XSYNC] Sync done: OK, 1 new, 0 deleted, 0 skipped, 0 failed
```

- Server `delivered_at` 2026-10-06T21:49:01Z (sha256-verified ack).
- LAN-first worked: `http://192.168.1.157:8781` answered in 146 ms; no tunnel used.
- SNTP succeeded on home Wi-Fi (`RTC set`).

## Findings

- Auto-join gives up per saved network after 7.0 s; the extender needs ~8.3 s, so auto-fallback to home Wi-Fi failed and the network had to be picked manually (same saved password). Plan risk r25.
- The slow step is the SD free-space query (6,988 ms), not the LAN probe. Plan risk r21.
