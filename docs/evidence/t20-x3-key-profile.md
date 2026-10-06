# t20 evidence: X3 key profile build checked by the operator

Date: 2026-10-07. Fork `feat/issue-1` at `04b1e1fd` (deviation d5 plus fixes E
and F), with `43676ff6` (deviation d6) on top, flashed app-only at 0x10000
(esptool "Hash of data verified" each time).

The operator reported on the device:

| Check | Result |
|-------|--------|
| Settings: side keys switch tabs, 4.3 / 4.4 move rows | "tested", works |
| Hold 4.1 in the reader rotates portrait and landscape | works; the operator prefers the other direction (changed in `1c58a24b`, see below) |
| Top-key reset off USB boots normally instead of sleeping | works |
| Wi-Fi auto-fallback to the second saved network (fix E) | "Fallback works" |
| Sync without the 7 s free-space pause (fix F) | "confirmed" |
| Hold 4.2 zoom mode | "Zoom works great" (`t20-zoom-mode.md`) |
| Paragraph scroll 4.3 / 4.4 (d6) | "perfect", with an occasional double press (r27, `t20-paragraph-scroll.md`) |

The top-key reset while USB is charging still goes to charge-sleep; the
operator accepted that ("I can't read while it's on").

Rotation now goes portrait to Landscape CCW (and Inverted to Landscape CW),
fork `1c58a24b`. Not yet checked on the device.
