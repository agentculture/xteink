# home clock minute tick

> The X3's home screen shows a clock that ticks over every minute while the device is awake, and stops costing anything once it sleeps

## Audience

- The X3 owner looking at the Home screen between books

## Before → After

- Before: Today the Home header clock (Settings > System > Clock > Show on home, off by default per CrossPointSettings.h:264) shows the time of the last redraw and goes stale until a button press
- After: While the X3 sits awake on Home, the header shows the correct local time, changing within ~10 s of each minute boundary, with a ghost-clearing half refresh every 15 minutes, and it still auto-sleeps on its normal timeout

## Why it matters

- The X3 doubles as a glanceable bedside/desk clock without a separate device, and the time stays right because the daily sync keeps the RTC honest

## Requirements

- HomeActivity::loop() (HomeActivity.cpp:303, no timer today) checks halClock.getTime() and calls requestUpdate() when the local minute differs from the last drawn minute, so both the classic and cover-grid Home layouts tick
  - honesty: A host or on-device check shows exactly one requestUpdate per minute change and none between changes (no redraw storm from the 50 ms idle loop)
- The minute tick only runs when the clock is actually shown (clockShowInHeader on and halClock.isAvailable()), so a hidden clock costs no extra refreshes
  - honesty: With Show on home off or no RTC, Home issues zero timer-driven refreshes
- Show on home defaults ON: CrossPointSettings.h:264 clockShowInHeader initializer becomes 1 for the xteink build
  - honesty: A freshly flashed/settings-wiped device shows the clock on Home without any user action
- Home keeps a minute-tick counter and renders every 15th tick with `HALF_REFRESH` instead of `FAST_REFRESH` (HomeActivity.cpp:482/559); the counter lives in HomeActivity only and never touches lastActivityTime or preventAutoSleep, so sleep timing is unchanged
  - honesty: Over 30 awake minutes on Home, exactly 2 `HALF_REFRESH` renders occur (ticks 15 and 30); all other ticks are `FAST_REFRESH`
- When the daily routine's Wi-Fi join gets an SNTP answer (trustedtime::startSync in the routine port's joinWifi, callback onTimeSynced in lib/TrustedTime/TrustedTime.cpp:55-70), the routine writes the synced UTC time to the RTC from its own task before Wi-Fi turns off, never from the lwIP callback (which would race the render task's I2C RTC reads via HalClock)
  - honesty: The RTC write happens off the lwIP task and only after SNTP reports completed; with no internet the RTC is left untouched
- HalClock's poll-and-cache (HalClock.cpp:37-54: `_cachedUtc`, `_lastPollMs`, `_hasCachedTime`, no lock) is guarded so the main-loop minute tick and the render task's formatTime can both call it without a torn 64-bit cache read or interleaved RTC I2C transactions
  - honesty: No HalClock member is read or written outside the guard; a host test or code review shows both callers go through it
- The daily routine's RTC write uses a new TZ-free HalClock setter (write UTC to the RTC + refresh the cache), never HalClock::syncFromNTP, which rewrites the process TZ via configTzTime (HalClock.cpp:88-93) — the exact TZ churn DailyRoutine.cpp:26-29 forbids because it races the render task
  - honesty: grep shows the routine never calls syncFromNTP/configTzTime/setenv(TZ) on the RTC-write path
- The xteink default-ON for Show on home is behind an xteink build flag set in the xteink envs (platformio.ini env:default / env:`xteink_release`), not a bare change to the shared CrossPointSettings.h:264 initializer, which every board env (x4pro, papermono, `eego_a4`, ...) also compiles
  - honesty: A non-xteink env build (e.g. x4pro) still defaults clockShowInHeader to 0
- The minute-tick and refresh-mode decision (minute changed? which tick is the 15th?) is a pure function covered by the fork's host tests (test/, as SntpPolicy.h is), and each tick logs one line with the minute and FAST/HALF so the 16-minute on-device check (c20) can be read from a serial log
  - honesty: Host tests cover minute change, no change, the 15th-tick HALF, and counter reset on Home re-entry

## Honesty conditions

- Ticking happens only while awake on Home; no tick logic runs in SleepActivity or after deep sleep
- With the tick running, auto-sleep fires at sleepTimeoutMinutes after the last button press, same as with the clock off
- The only person reading the X3 Home screen is its owner; no multi-user behavior is needed
- Confirmed on the current X3 build: the header clock does not change without a button press
- Verified on the X3 itself, not only in host tests
- The clock is accurate enough to be relied on (within 10 s display lag, RTC within 2 s after a sync)
- Measured on the X3 with a reference clock, results recorded in docs/evidence/
- Measured after a real morning daily sync, recorded in docs/evidence/

## Success signals

- On the X3, Home left awake for 16 min shows 16 consecutive minute changes, each within 10 s of a reference clock, exactly 1 half refresh (at tick 15), and the device enters sleep at sleepTimeoutMinutes +/- 10 s after the last button press
- After a daily sync with internet reachable, the RTC differs from NTP time by < 2 s (checked via Clock settings row or the \[DAILY\] serial log)

## Scope / boundaries

- The tick must not keep the device awake: requestUpdate() never touches lastActivityTime (main.cpp:819-824), so auto-sleep at sleepTimeoutMinutes (main.cpp:897-901) still fires on schedule

## Non-goals

- No clock while sleeping: deep sleep is a full chip reset (main.cpp:171-177) and SleepActivity renders no time; the sleep image is unchanged
- Reader screens are untouched: the reader's status-bar clock is the separate statusBarClock setting (SettingsList.h:501) and is out of scope

## Assumptions

- Clock rendering already exists and is reused, not rebuilt: the X3 board profile has a DS3231 RTC (freeink-sdk BoardConfig.h:959), halClock.isAvailable() is true on X3, and the Xteink theme draws a centered header clock on Home gated by SETTINGS.clockShowInHeader && halClock.isAvailable() (BaseTheme.cpp:374-376, XteinkTheme.h:39, HomeActivity.cpp:509, CoverGridHomeUi.cpp:145)
- Each tick is a full-panel `FAST_REFRESH` (HomeActivity.cpp:482/559): Uc8253X3Driver does not override displayWindow, so PanelDriver.h:54 falls back to a whole-screen fast refresh, the same visual cost as a page turn
- The displayed minute may lag the RTC by up to 10 s because HalClock caches the RTC read for `CLOCK_POLL_MS` (HalClock.h:17, HalClock.cpp:41); acceptable for a minute clock

## Scope exploration

- `s1` — `lib/hal/HalClock + freeink-sdk BoardConfig.h`: X3 has a DS3231 RTC at 0x68 (BoardConfig.h:959); localTime caches RTC reads 10 s; RTC written only by ClockSync and first Wi-Fi join
  - seeds: `c2`, `c9`, `q3` (question, resolved)
- `s2` — `src/components/themes (BaseTheme, XteinkTheme) + ClockSettingsActivity`: Home header already draws a centered clock when Show on home (clockShowInHeader, default 0) is on; nothing redraws it on a timer
  - seeds: `c2`, `c11`, `q1` (question, resolved)
- `s3` — `src/activities/home/HomeActivity.cpp`: loop() at :303 is input-only; render() repaints the full screen with `FAST_REFRESH` (:482 cover-grid, :559 classic); a minute-change check + requestUpdate() is the insertion point
  - seeds: `c3`, `c4`
- `s4` — `src/main.cpp sleep + SleepActivity`: auto-sleep keys off lastActivityTime, reset only by input or preventAutoSleep (:819-824, :897-901); self-requested redraws don't reset it; sleep is deep sleep/chip reset with no clock on the sleep image
  - seeds: `c5`, `c6`
- `s5` — `freeink-sdk FreeInkDisplay PanelDriver + Uc8253X3Driver`: X3 driver has no displayWindow override; PanelDriver.h:54 falls back to whole-screen Fast refresh, so no partial clock-only refresh on X3 without driver work
  - seeds: `c8`, `q2` (question, resolved)
- `s6` — `src/SettingsList.h statusBarClock`: reader status-bar clock is a separate setting; reader is out of scope
  - seeds: `c7`
- `s7` — `lib/TrustedTime/TrustedTime.cpp + DailyRoutine.cpp port`: routine's joinWifi starts background SNTP (trustedtime::startSync); onTimeSynced runs on the lwIP task; chooseLocalClock (DailyRoutine.cpp:265) prefers system/RTC so SNTP is not awaited; nothing writes SNTP time to the RTC except ClockSync and first Wi-Fi join
  - seeds: `c17`
- `s8` — `src/CrossPointSettings.cpp toJson/load`: every persisted key is written (toJson loop :68) and a saved value overrides the initializer on load (:122), so changing the clockShowInHeader default does not flip the user's already-provisioned X3
  - seeds: `c15`
- `s9` — `DailyRoutine.cpp port timezone() + Timezones`: shipped clock default is UTC (clockTimezone 255); the routine falls back to Asia/Jerusalem only for its 06:00 rule, so an unset device shows UTC on the Home clock
  - seeds: `c2`
- `s10` — `challenge pass / concurrency lens: lib/hal/HalClock.cpp`: localTime mutates an unlocked cache; today only the render task (and the pre-activity routine) call it; the tick adds a second caller on the main task
  - seeds: `c22`
- `s11` — `challenge pass / adjacent-systems lens: HalClock::syncFromNTP + DailyRoutine.cpp:26-29`: the only existing RTC-write path rewrites TZ; the routine's own comment forbids TZ churn, so c17 needs a new TZ-free setter
  - seeds: `c23`
- `s12` — `challenge pass / overlooked-actors lens: BoardConfig.h RtcType + platformio.ini envs`: X3 (DS3231) is one of many boards; PCF8563/RX8130 boards also have RTCs, so a shared-initializer default change reaches non-xteink builds and the fork's upstream-facing diff
  - seeds: `c24`
- `s13` — `challenge pass / observability lens: success signals c20/c21 + fork test/ host tests`: nothing today would let the 16-minute check count half refreshes; needs a per-tick log line and a host-testable decision function. Opening the X3 serial port resets it (x3-flash-protocol), so start the 16 min after the port is open
  - seeds: `c25`
- `s14` — `challenge pass / security lens: clock tick + RTC write`: clean pass: no new network surface, input, or secret; SNTP servers and trust unchanged (TrustedTime.cpp configureSntp). Residual: none identified
- `s15` — `challenge pass / reversibility + rollback lens: OTA + settings`: firmware is reversible by offering an older build (OTA flow, docs/firmware-release.md); a default change is reversible; only the q4 migration would rewrite a user's saved choice
- `s16` — `challenge pass / lifecycle lens: Home entry/exit, TZ/DST change, RTC jump`: a minute mismatch from a TZ change, DST shift, or RTC write simply triggers one redraw; tick counter must reset when Home is re-entered (seeded into c25); not examined: Home sub-states such as recents loading (HomeActivity recentsLoading) beyond the explorer's guard note

## Decisions

- Show on home (clockShowInHeader) defaults ON in the xteink firmware build
- Home runs a `HALF_REFRESH` every 15 minute-ticks; ticking and the refresh counter never block or delay auto-sleep
- The daily sync writes its SNTP time to the RTC so the clock stays correct without manual Sync now
- No settings migration: the existing X3's Show on home is flipped once by the user; the new default covers fresh/reset devices
- The xteink build flag also defaults the clock time zone to Asia/Jerusalem when none is chosen
- The routine waits up to 8 s (kClockSyncBudgetMs) for SNTP before writing the RTC, only if SNTP has not already answered, within the 105 s routine cap
- The minute tick runs even when Time to sleep = Never

## Hard questions

- Is the existing device toggle (Settings > System > Clock > Show on home, default off) the switch, or should the xteink build default it on? (resolved: Firmware default: the xteink build ships Show on home (clockShowInHeader) ON)
- The RTC is only written by Clock > Sync now and the first Wi-Fi join (ClockSyncActivity.cpp:67, WifiSelectionActivity.cpp:533-537); the daily sync's SNTP sets system time only. Should the daily sync also write its SNTP answer to the RTC, so the clock stays correct without manual syncs? (resolved: Yes: when the daily sync's SNTP answer arrives, write it to the RTC)
- With no time zone picked, the clock shows UTC. Should the xteink build default the clock time zone to Asia/Jerusalem (matching the 06:00 rule), or keep UTC and set it on the device? (resolved: Default the clock time zone to Asia/Jerusalem behind the same xteink build flag)
- With Time to sleep = Never (sleepTimeoutMinutes 31, getSleepTimeoutMs returns 0 at CrossPointSettings.cpp:364) Home would refresh 1440 times + 96 half refreshes a day on battery. Tick anyway, or only tick on USB power / when a sleep timeout is set? (resolved: Tick anyway when Time to sleep = Never; the user chose never on purpose)
- Accept a whole-screen fast refresh each minute with ghosting building until the next half refresh, or add a periodic `HALF_REFRESH` every N ticks (Home has no ghosting counter; the reader's pagesUntilFullRefresh at ReaderActivity.cpp:27 is the existing pattern)? (resolved: Home does a `HALF_REFRESH` every 15 minute-ticks to clear ghosting; the counter never blocks or delays auto-sleep)
- Your X3 already stores clockShowHeader=0, so a new default won't reach it. Add a one-time settings migration that turns it on for existing devices (it would also override anyone who deliberately turned it off), or will you flip the toggle once on the device? (resolved: No migration: the user flips Show on home once on the existing X3; the new default covers fresh/reset devices)
- Background SNTP (trustedtime::startSync) often hasn't answered when a quick LAN sync turns Wi-Fi off (SntpPolicy.h:13 notes tens of seconds on a hotspot), so the RTC write might rarely happen. Wait a bounded time (e.g. up to kClockSyncBudgetMs = 8 s, inside the 105 s routine cap) for SNTP at the end of the routine, or best effort only? (resolved: At the end of the daily routine, if SNTP has not answered yet, wait up to kClockSyncBudgetMs (8 s) inside the 105 s cap, then write the RTC; skip the wait when it already answered)

## Open parks

- [unknown_nonblocking] Whether 15-minute `HALF_REFRESH` keeps ghosting acceptable on the X3's UC8253 fast LUT is unmeasured; only the on-device run (c20) will show it
- [unknown_nonblocking] Whether the X3's DS3231 keeps time when the main battery is fully drained (backup cell fitted?) is not verifiable from code; the RTC write in c17 and Sync now recover it
