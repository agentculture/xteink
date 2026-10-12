# Delivery Summary — home clock minute tick

plan: `home-clock-minute-tick` · run: `partial` · date: `2026-10-12`
baseline: `devague summary skeleton`

## Intent

> The X3's home screen shows a clock that ticks over every minute while the device is awake, and stops costing anything once it sleeps

After: While the X3 sits awake on Home, the header shows the correct local time, changing within ~10 s of each minute boundary, with a ghost-clearing half refresh every 15 minutes, and it still auto-sleeps on its normal timeout

The run is `partial` because t8 (the morning RTC check) can't run before 2026-10-13. t7's serial measurement also wasn't run: the minute tick is confirmed by the owner on the device, but its timing, the 15-tick half refresh and the sleep timing are not measured.

## Planned Work

Quoted verbatim from the `devague summary` skeleton:

- `t1` — HalClock: guard the poll/cache and add a TZ-free UTC setter
- `t2` — Pure minute-tick decision function with host tests
- `t3` — xteink build flag: Show on home ON and Asia/Jerusalem clock TZ by default
- `t4` — Home: tick the header clock every minute with a half refresh every 15 ticks
- `t5` — Daily routine: wait up to 8 s for SNTP, then write the RTC
- `t6` — Fork PR, gates, merge, and release the build to the X3 server
- `t7` — On-device: install via Check for updates, flip Show on home, run the 16-minute Home check
- `t8` — Morning check: RTC within 2 s of NTP after a real daily sync
- `t9` — xteink repo closeout: evidence, prompt-file facts, version bump, PR

## Actual Delivery

| Plan task | Status | What actually landed |
|-----------|--------|----------------------|
| `t1` | delivered | Fork `f3ef5052`: a FreeRTOS mutex with an RAII `ClockLock` guarding the HalClock cache and every RTC call, and a new `HalClock::setUtc(epoch)` with no TZ calls. `syncFromNTP` now uses it and waits unlocked. |
| `t2` | delivered | Fork `c64e78a4`: `src/xteink/ClockTick.h` (`xteink::clocktick::step`, constexpr, `HALF_EVERY_TICKS = 15`) and 10 host tests in `test/xteink_clock_tick/`. |
| `t3` | delivered | Fork `516b4218`: `-DXTEINK_CLOCK_DEFAULTS` in `env:default` and `env:xteink_release` only. `clockShowInHeader` is 1 under the flag. The clock zone falls back to Asia/Jerusalem (`JERUSALEM_INDEX = 23`, static_assert); the stored zone stays 255. |
| `t4` | delivered | Fork `024a5c53` and `67acc1f9`: Home polls the clock once a second, decides through `clocktick::step` and calls `requestUpdate()`. Every 15th tick renders `HALF_REFRESH` through an atomic flag that the render task consumes. Later moved into `HomeActivity::pollClockTick()` (`6af6bedd`, `498dc69d`, for SonarCloud). |
| `t5` | delivered | Fork `37ebdb92`, `0bd9c52e`, `b22f6c0c`: the RoutinePort gains `sntpCompleted`, `waitSntp` and `writeRtc`. `syncRtc()` waits at most min(8 s, remaining cap), then writes the RTC. The `[DAILY]` line gains `rtc_written`. Also fixed: a fast RTC was never corrected (reviewer finding), and an earlier SNTP answer was overwritten by the RTC. |
| `t6` | delivered | Fork PR agentculture/xteink-firmware#4 was squash-merged as `2b3cbdea`: 18/18 checks green, SonarCloud at 0 open issues (one false positive and two accepted, each with a comment). It was released with `xteink firmware release 4` (d1) as `1.6.5+xteink.2b3cbdea`, offered to x3-ori (#3), with the PR comment posted. |
| `t7` | partial | Criteria 1 and 2 were met by owner observation: "bug confirmed" on `c6e8b2cf`, and "fix confirmed" after the install. The server shows x3-ori on `1.6.5+xteink.2b3cbdea`. Criterion 3, the 16-minute serial log, was not run. Recorded in `docs/evidence/home-clock-validation.md`. |
| `t8` | blocked | Needs the first daily run after 06:00 on 2026-10-13. |
| `t9` | partial | Prompt facts are in `CLAUDE.md`, `QWEN.md`, `AGENTS.override.md`, `AGENTS.colleague.md` and `.pi/SYSTEM.md`. The version is bumped to 0.12.0 with a CHANGELOG entry. All gates pass. The colleague review and the PR (stacked on `ota/daily-sync`, the base the owner chose) are still in progress. t9 formally depends on t8 and was started early at the owner's request. |

## Mid-work Decisions

- `d1` — before t6, fold scripts/firmware-release.py into the xteink CLI as `'xteink firmware release <pr>'` and 'xteink firmware report-rollbacks', delete the script; t6 ships fork PR #4 with 'xteink firmware release 4' instead of the script — CLAUDE.md requires product components under a CLI noun group, not a separate entry point; the script (ac1515c, OTA plan) broke that rule and the user asked for it to be part of the CLI
- `TrustedTime::syncNow` fix (fork `abf91c8c`, delta `b2`). Found in the owner's `/code-review`: ESP-IDF clears `SNTP_SYNC_STATUS_COMPLETED` when it is read, so a successful sync was reported as failed. This bug is in the released `c6e8b2cf` build. No deviation record covers it, because it fixes code t5 depends on rather than changing a task.
- When SNTP already answered this boot, the routine uses the system clock as network time instead of adopting the RTC (fork `b22f6c0c`, delta `b3`). This came from the same review.
- The Home tick polls once a second and honours the theme's `headerShowsClock` (fork `67acc1f9`, delta `b4`). This came from the same review.
- SonarCloud triage. Ten issues were fixed. S8379 was marked a false positive, and S6229 and S1121 were accepted, each with a comment. The S2681 issue introduced by the refactor was fixed in `498dc69d`.
- The fork merge waited for the owner's explicit "Squash merge", because auto mode blocked the agent's first merge attempt. The release was then run as the plan's t6.
- PR base: stacked PRs, chosen by the owner. The OTA closeout (0.11.0) goes to `feat/issue-1`, and this work (0.12.0) to `ota/daily-sync`.
- The colleague review for the first fork PR timed out at 900 s, and an Opus reviewer subagent was used instead. Its finding (a fast RTC never corrected) was fixed test-first in `0bd9c52e`.

## Drift From Plan

| Plan item | Reason for divergence | Classification |
|-----------|------------------------|-----------------|
| `t6` (`d1`) | CLAUDE.md requires product components under a CLI noun group, not a separate entry point; the script (ac1515c, OTA plan) broke that rule and the user asked for it to be part of the CLI | `acceptable` |
| `t7` | The 16-minute serial log (criterion 3) was not run. Owner observation replaces it for "it ticks", while the timing, the single HALF at tick 15 and the sleep timing are unmeasured | `needs-follow-up` |
| `t8` | Not yet run: it needs a real 06:00 daily sync | `needs-follow-up` |
| `t9` | Started before t8, its declared dependency, at the owner's request. Its evidence will not include t8 | `acceptable` |
| `t5` | The `TrustedTime::syncNow` fix and the system-clock preference when SNTP already answered go beyond t5's contract (deltas `b2`, `b3`) | `acceptable` |

## Evidence

- tests (fork, at `498dc69d`, tree-identical to the merge `2b3cbdea`): `ctest --test-dir build/test`, 707/707 pass. The 36 clock-related tests (`ClockTick.*`, `DailyRtc.*`, `*Jerusalem*`, `TrustedTimeTimezone`) were re-run on 2026-10-12T20:41:32Z and pass.
- tests (fork): `python3 test/test_trusted_time.py` passes.
- builds (fork): `pio run -e default` and `pio run -e x4pro` succeed at `498dc69d`.
- tests (xteink, at `025df88`): `uv run pytest -n auto`, 565 passed, 3 skipped. `tests/test_firmware_release.py` (17) drives `xteink firmware release` / `report-rollbacks`.
- lint (xteink): black, isort, flake8, bandit, markdownlint (0 errors), `teken cli doctor --strict`, `scan-secrets.py` and `harness-smoke.py --stage config` (6 passed) are all clean.
- lint (fork): `./bin/clang-format-fix` exits 0, and SonarCloud has 0 open issues on PR #4.
- devague records: evidence `e1`–`e7`, deltas `b1`–`b4`, lapse `l1` (all proposed) and deviation `d1` (approved).
- commits: fork `c6e8b2cf..2b3cbdea` (one squash), and xteink `a7a580d..025df88` on `clock/home-minute`.
- PRs: agentculture/xteink-firmware#4 (merged). xteink PRs to follow, stacked.
- device: `xteink device list --json` shows device 3 on `xteink-fw 1.6.5+xteink.2b3cbdea`.

## Delivery Claims

Confidence is capped while the evidence records are still `proposed`: they await the owner's adjudication.

| Claim | Confidence | Evidence |
|-------|------------|----------|
| `c3`: Home redraws the header clock when the local minute changes, and not otherwise | medium | `e1` (ClockTick tests, decision function only) · `e2` (owner observation on x3-ori) · fork `67acc1f9`, `498dc69d` |
| `c4`: a hidden clock or a missing RTC costs no extra refreshes | unverified | no test. The gate is in `HomeActivity::pollClockTick()`, read in code only |
| `c5`: the tick does not keep the device awake; auto-sleep fires on schedule | unverified | no test and no on-device measurement (t7 criterion 3 not run) |
| `c16`: every 15th tick since entering Home is HALF, the rest FAST; the count restarts on re-entry | medium | `e3` (ClockTick.Tick14/15/16/30, ResetOnReentry; the decision only, not the render wiring) |
| `c17`: the routine waits at most min(8 s, cap) for SNTP and then writes the RTC from its own task | medium | `e5` (DailyRtc tests against a fake port). The on-device check, t8, is pending |
| `c22`: HalClock is safe to call from the main loop, the render task and the routine | unverified | no concurrency test. The mutex in fork `f3ef5052` is read in code only |
| `c23`: the RTC write is TZ-free and happens only after SNTP answered | low | `e4` (the routine side, with a fake port). The setenv/tzset-free `setUtc` is not asserted by a test, and lapse `l1` (proposed) bears on these fakes |
| `c24`: under the xteink flag, Show on home defaults on and the zone defaults to Jerusalem; other envs are unchanged | low | `e6` (build check and static_assert only). A fresh-device default is not proven (plan risk r1) |
| `c25`: the tick decision is a pure, host-tested function | high | `e7` · `test/xteink_clock_tick/` · fork `c64e78a4` |
| the release flow is a CLI verb and shipped this build | high | `b1` · `tests/test_firmware_release.py` · PR #4 release comment · device 3 reports `1.6.5+xteink.2b3cbdea` |

Lapse ledger evidence:

pending approval (not yet evidence): `l1`

## Remaining Work / Follow-up

- `t8`: after the first daily run past 06:00 on 2026-10-13, check `rtc_written yes` and that the RTC is within 2 s of NTP. Owner and agent.
- `t7` criterion 3: the 16-minute serial check (16 ticks within 10 s, exactly one HALF, sleep on time), or the owner's decision to accept the visual check. Owner decision.
- `c4`, `c5`, `c22` are untested: they need on-device measurement (the t7 serial run) or a host test seam for HomeActivity and HalClock. Follow-up.
- Adjudicate evidence `e1`–`e7`, deltas `b1`–`b4` and lapse `l1`: confirm or reject each. Owner.
- `t9`: finish the colleague review and open the stacked xteink PRs (OTA 0.11.0 → `feat/issue-1`, then this one at 0.12.0 → `ota/daily-sync`). Agent.
- Plan risk r4: the web settings page shows the raw clock zone 255 when none is chosen. Follow-up.
- Plan risk r1: the "default on" for Show on home is unproven on a wiped device. Open until a spare device exists.
- OTA plan: the (a′) `last_fw_outcome=installed` check after 06:00 on 2026-10-13 (see `docs/evidence/ota-daily-validation.md`).
