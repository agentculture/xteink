# Home clock minute tick: on-device validation

Plan `home-clock-minute-tick`, task t7. Device: x3-ori (device #3).

## Release (t6)

Fork PR agentculture/xteink-firmware#4 was squash-merged into `feat/issue-1` as `2b3cbdea` at
the owner's explicit request. All 18 checks were green, and SonarCloud showed 0 open issues
(S8379 marked as a false positive, S6229 and S1121 accepted, each with a comment).

`uv run xteink firmware release 4 --fork-checkout ~/git/xteink-firmware` exited 0. This was the
first run through the CLI verb (deviation d1). It printed
`{"version": "1.6.5+xteink.2b3cbdea", "sha": "2b3cbdea…", "offered": [3]}`, posted the signed
release comment on PR #4 (device x3-ori (#3) offered, 2 revoked devices skipped), and removed its
temporary worktree. Nothing was flashed over serial.

## t7 acceptance

| Criterion | Result | Evidence |
|-----------|--------|----------|
| Before the install, the header clock does not change without a button press (c11) | **Met** | The owner observed it on `1.6.5+xteink.c6e8b2cf` and reported "bug confirmed" (2026-10-12) |
| After the install, Settings > System > Clock > Show on home is turned on, and the clock ticks | **Met (visual)** | The owner installed via Check for updates and reported "fix confirmed". `xteink device list` shows x3-ori on `xteink-fw 1.6.5+xteink.2b3cbdea` |
| 16-minute serial log: 16 tick lines within 10 s of a reference clock, exactly one HALF at tick 15, sleep at the timeout ± 10 s | **Not run** | Serial wasn't opened. Without it, the tick count, the timing tolerance, the single HALF and the sleep timing are not measured |

## Not established

- The per-minute timing accuracy, the 15-tick HALF cadence and the sleep timing on the device.
  The host test `test/xteink_clock_tick/` covers the cadence logic (first reading records only,
  a minute change redraws, every 15th tick is HALF). On-device timing and sleep remain unmeasured.

## Next

- t8 (morning of 2026-10-13, after the 06:00 run): the `[DAILY]` line shows `rtc_written yes`,
  and the RTC is within 2 s of NTP.
