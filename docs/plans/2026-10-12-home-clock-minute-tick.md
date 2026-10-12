# Build Plan — home clock minute tick

slug: `home-clock-minute-tick` · status: `exported` · from frame: `home-clock-minute-tick`

> The X3's home screen shows a clock that ticks over every minute while the device is awake, and stops costing anything once it sleeps

## Tasks

### t1 — HalClock: guard the poll/cache and add a TZ-free UTC setter

- instruction: Fork repo agentculture/xteink-firmware, branch off feat/issue-1 (c6e8b2cf). Keep syncFromNTP's behavior; just route its cache/RTC writes through the guard. A recursive or non-recursive mutex is fine as long as public methods do not re-enter each other while holding it. No AI trailers in fork commits.
- covers: c22, h14
- acceptance:
  - lib/hal/HalClock.{h,cpp} only: a FreeRTOS mutex (or portMUX critical section) guards every read/write of `_cachedUtc`, `_hasCachedTime`, `_lastPollMs` and every `_sdkRtc` call; localTime/getTime/formatTime/syncFromNTP/setTimezone all take it
  - new bool HalClock::setUtc(`int64_t` epoch) writes the RTC via `_sdkRtc`.set and refreshes the cache under the guard; it calls none of setenv, tzset, configTzTime (grep-verifiable)
  - pio run -e default builds with no new warnings; clang-format-fix clean

### t2 — Pure minute-tick decision function with host tests

- instruction: Mirror src/network/SntpPolicy.h + test/`xteink_sync` style. Host test build: cmake -S test -B build/test -G Ninja && cmake --build build/test && ctest --test-dir build/test. This task owns test/CMakeLists.txt.
- covers: c25, h17
- acceptance:
  - new header-only src/xteink/ClockTick.h (no Arduino/HAL includes) exposes a function taking (lastMinute or none, nowMinute, ticksSinceHomeEntered) and returning {redraw, half}: redraw only when the minute changed; half on the 15th, 30th, ... tick; first observation after Home entry draws nothing extra
  - new test/`xteink_clock_tick` host test registered in test/CMakeLists.txt covers: unchanged minute, minute change, hour/day wrap (59->0), tick 14 FAST, tick 15 HALF, tick 30 HALF, reset on re-entry; ctest passes

### t3 — xteink build flag: Show on home ON and Asia/Jerusalem clock TZ by default

- instruction: Files: platformio.ini, src/CrossPointSettings.h, src/util/Timezones.cpp only. Check whether timezones::activeIndex()/applyToClock treat clockTimezone 255 as UTC; make the flag change that fallback, not the stored value. The daily routine's own Jerusalem fallback (DailyRoutine.cpp routineTimezone) stays as is.
- covers: c15, h5, c24, h16
- acceptance:
  - a build flag (e.g. -`DXTEINK_CLOCK_DEFAULTS`) is set in the xteink envs of platformio.ini (env:default and env:`xteink_release`); with it, CrossPointSettings.h clockShowInHeader initializes to 1 and an unset clock time zone resolves to the Jerusalem entry (Timezones.cpp:38); without it both stay as today
  - pio run -e default and pio run -e x4pro both build; a host or static check shows x4pro keeps clockShowInHeader = 0
  - a saved settings file value still overrides the default (load path at CrossPointSettings.cpp:122 untouched)

### t4 — Home: tick the header clock every minute with a half refresh every 15 ticks

- instruction: Depends on t1 (thread-safe getTime) and t2 (ClockTick.h). Keep the change minimal and inside HomeActivity.
- depends on: t1, t2
- covers: c1, h1, c3, h2, c4, h3, c5, h4, c16, h6
- acceptance:
  - src/activities/home/HomeActivity.{h,cpp} only: loop() calls halClock.getTime only when SETTINGS.clockShowInHeader && halClock.isAvailable(), feeds ClockTick, and calls requestUpdate() exactly when it says redraw; nothing is ticked when the clock is hidden
  - render() uses `HALF_REFRESH` when the tick said half, otherwise its existing mode, on both the cover-grid (:482) and classic (:559) paths; tick count resets in onEnter
  - no write to lastActivityTime and no preventAutoSleep override added (grep); each tick logs one `LOG_INF` line with HH:MM and FAST/HALF
  - no tick redraw while recents are loading (recentsLoading guard)

### t5 — Daily routine: wait up to 8 s for SNTP, then write the RTC

- instruction: Do not touch test/CMakeLists.txt (t2 owns it); extend the existing test/`xteink_daily` target. The write happens on the routine's task, never from TrustedTime's onTimeSynced callback.
- depends on: t1
- covers: c17, h7, c23, h15
- acceptance:
  - src/xteink/DailyRoutine.{h,cpp}: Port gains sntpCompleted()/waitSntp(budget) and writeRtc(epoch) (implemented via HalClock::setUtc); before wifiOff the routine, when Wi-Fi was up, waits at most min(kClockSyncBudgetMs, remaining cap) only if SNTP has not completed, then writes the RTC on success
  - on SNTP timeout or no internet the RTC is untouched and the run's status/outcomes are unchanged; the \[DAILY\] log line reports `rtc_written` yes/no
  - test/`xteink_daily` host tests (fake Port) cover: already-synced (no wait, RTC written), late sync within budget, timeout (RTC untouched), cap nearly exhausted (wait clipped); ctest passes
  - the RTC write path calls none of syncFromNTP, configTzTime, setenv, tzset (grep)

### t6 — Fork PR, gates, merge, and release the build to the X3 server

- instruction: Follow docs/firmware-release.md and the x3-flash-protocol memory. No direct flashing: the X3 gets it via Settings > Check for updates (OTA), like c6e8b2cf did.
- depends on: t3, t4, t5
- acceptance:
  - fork PR feat(xteink): home clock minute tick into feat/issue-1, conventional-commit title, no AI trailers; clang-format-fix clean (exit status checked), host ctest green, pio run -e default and -e x4pro green, harness-smoke all, Sonar gate checked
  - after merge, uv run python scripts/firmware-release.py release <forkPR#> --fork-checkout <fork worktree> uploads and offers 1.6.5+xteink.<sha8> to device 3; the PR comment is posted

### t7 — On-device: install via Check for updates, flip Show on home, run the 16-minute Home check

- instruction: Read the x3-flash-protocol and network-identifier-hygiene memories first. Kill loggers by PID. Leave the device untouched during the 16 minutes.
- depends on: t6
- covers: c18, h8, c20, h12, c11, h10, c10, h9, c19, h11
- acceptance:
  - before the install, the user confirms on the current build that the header clock does not change without a button press (c11)
  - after the install the user turns on Settings > System > Clock > Show on home and picks a time zone if the clock shows UTC
  - with the user's OK to open serial (it resets the X3), a 16-minute serial log on Home shows 16 tick lines, each within 10 s of a reference clock, exactly one HALF (tick 15), then the device sleeps at sleepTimeoutMinutes +/- 10 s after the last press; recorded in docs/evidence/home-clock-validation.md with SSIDs redacted

### t8 — Morning check: RTC within 2 s of NTP after a real daily sync

- instruction: Prefer a serial log captured with the user's OK; otherwise compare the Clock settings row against a reference clock by eye and say so in the evidence.
- depends on: t7
- covers: c21, h13
- acceptance:
  - after the next 06:00 daily sync with internet, the \[DAILY\] line shows `rtc_written` yes and the clock differs from an NTP reference by < 2 s; recorded in docs/evidence/home-clock-validation.md

### t9 — xteink repo closeout: evidence, prompt-file facts, version bump, PR

- instruction: Branch clock/home-minute sits on ota/daily-sync, which is still local and unmerged; confirm the PR base with the user before opening.
- depends on: t8
- acceptance:
  - CLAUDE.md, QWEN.md, AGENTS.override.md, AGENTS.colleague.md mention the Home clock tick and the RTC write in their firmware facts; markdownlint, black/isort/flake8, bandit, scan-secrets, teken cli doctor --strict, harness-smoke --stage config all pass
  - version-bump (minor) with a CHANGELOG entry; ask-colleague review run; PR opened via the cicd skill against the right base (ota/daily-sync's PR base chain)

## Risks

- [unknown_nonblocking] h5 says a fresh/settings-wiped device shows the clock without user action; proving it on the user's only X3 would wipe its settings, so t3 proves it by build/host check unless the user offers a device to wipe (task t3)
- [unknown_nonblocking] 15-tick `HALF_REFRESH` may not be enough against ghosting on the X3 UC8253 fast LUT (frame park v1); t7 will show it, and a change would be a /deviate (task t7)
- [follow_up] the clock/home-minute xteink branch stacks on the unpushed ota/daily-sync branch (itself on open PR #4); its PR base depends on how those land (task t9)
