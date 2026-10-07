# Delivery Summary — xteink end-to-end (issue 1)

plan: `xteink-end-to-end-issue-1` · run: `partial` · date: `2026-10-06`
baseline: `devague summary skeleton`

The run is `partial` for three reasons:

- `t24` (version bump, review, PRs) has not run yet.
- `t21` left the prompt files describing the firmware as unverified.
- Obligation `o26` (a 5 MB or larger EPUB over HTTPS on the X3) was never
  tested.

Every other task merged, and its evidence is listed below.

## Intent

Issue #1 asked for xteink end to end:

- **Server side:** one docker compose stack on spark serving the library API,
  the MCP server, the CLI-backed management and a React web UI from startup.
  It is reachable through cultureflare at `ebooks.culture.dev` (web UI) and
  `xteink.culture.dev` (device API).
- **Device side:** our own CrossPoint fork on the Xteink readers, with the X3
  first and every model building in CI. The firmware joins the "iPhone (5)"
  hotspot or home Wi-Fi, downloads books, and reads fully offline, driven by
  the reader's buttons.

The run executed the converged 24-task plan through `/assign-to-workforce`,
with TDD-gated merges and hardware validation on the operator's X3
(MAC `68:C6:3A:3B:C2:4C`).

> xteink ships end-to-end: one docker compose stack on spark serves the library API, MCP, CLI-backed management and a React web UI on startup, reachable at ebooks.culture.dev behind a key via cultureflare; Xteink readers (X3 first, all models) run our firmware that auto-joins a phone hotspot or home Wi-Fi, downloads books, and reads fully offline with a button-driven menu for pages and zoom

## Planned Work

Quoted verbatim from the `devague summary` skeleton:

- `t1` — Core library: storage, models and service layer (xteink/core/)
- `t2` — Ingest: upload containment and Markdown/HTML to EPUB conversion (xteink/core/ingest.py)
- `t3` — HTTP API: main app + device-only app, key auth (xteink/server/app.py, auth.py, `routes_library.py`)
- `t4` — Device protocol v1: endpoints + docs/device-protocol.md (xteink/server/`routes_device.py`)
- `t5` — MCP server with the official mcp SDK (xteink/mcp/)
- `t6` — CLI nouns as thin API clients: server, library, device, tunnel, mcp (xteink/cli/`_commands`/)
- `t7` — Web UI: Vite + React + TS app with the five flows (web/)
- `t8` — Docker image + compose stack with remote profile (Dockerfile, compose.yaml, docker/)
- `t9` — Playwright end-to-end flows against the compose stack (web/e2e/)
- `t10` — CI: web job, arm64 image build, egress-deny privacy test (.github/workflows/)
- `t11` — Remote access via cultureflare: two hostnames, dry-run then apply (docs/remote-access.md)
- `t12` — Firmware fork repo + CI matrix for every Xteink env (agentculture/xteink-firmware)
- `t13` — Fork: security hardening - pinned TLS verification, no open services, OTA from fork releases
- `t14` — Fork: button map, zoom mode and reader menu (input + reader activities)
- `t15` — Fork: xteink theme - boot, home and library screens designed for e-ink
- `t16` — Fork: serial provisioning handler (Wi-Fi networks, server URLs, device key)
- `t17` — Fork: xteink sync client (protocol v1), device key in NVS, LAN-first with tunnel fallback, status line
- `t18` — CLI: device backup and device provision over USB (xteink/cli/`_commands`/`device_usb.py`)
- `t19` — X3 bring-up: probe, stock backup, first flash, provisioning (hardware, MAC 68:C6:3A:3B:C2:4C)
- `t20` — Hardware end-to-end validation on the X3 and spark (evidence run)
- `t21` — Docs and prompt files: README quickstart, MCP/API docs, CLAUDE.md current state, harness prompts
- `t22` — /validate-delivery: run behavioral tests and file evidence for o1-o36
- `t23` — /summarize-delivery: planned vs actual accountability artifact
- `t24` — Version bump, ask-colleague review and PRs via cicd (xteink + fork)

## Actual Delivery

Repositories:

- **xteink:** branch `feat/issue-1`, `main..0731153` plus this artifact,
  local only and not pushed.
- **Fork:** `agentculture/xteink-firmware` branch `feat/issue-1`,
  `2f6a52c5..1c58a24b`, pushed.

| Plan task | Status | What actually landed |
|-----------|--------|----------------------|
| `t1` | delivered | `xteink/core/`: SQLite store, content-addressed blobs, library, devices and queue, keys. 99–100% line coverage. |
| `t2` | delivered | `xteink/core/ingest.py`: size cap, magic bytes, zip-bomb guards, pandoc `--sandbox` conversion. The real-pandoc test passes inside the image (privacy-check run). |
| `t3` | delivered | Main app on :8780 and device-only app on :8781, key auth, cited Cloudflare Access verifier (`xteink/server/access.py`), `api/openapi.json` drift check. |
| `t4` | delivered | `/api/device/*` protocol v1 (queue, download with Range, sha256 ack, status, mirror deletes, sd_full) and `docs/device-protocol.md`. |
| `t5` | delivered | `xteink/mcp/` on the official SDK with `push_file`, `list_library` and `send_to_device`, over stdio and streamable HTTP on :8782. |
| `t6` | delivered | CLI nouns `server`, `library`, `device`, `tunnel`, `mcp`. Dry-run unless `--apply`. `teken cli doctor --strict` passes. |
| `t7` | delivered | `web/` Vite + React UI with five flows. SSO-only on ebooks.culture.dev (`d4`). |
| `t8` | delivered | `Dockerfile` (pandoc 3.12), `compose.yaml` with `api` and `mcp`, plus `cloudflared-ui` and `cloudflared-device` under the `remote` profile. |
| `t9` | delivered | `web/e2e/` with 5 Playwright flows against a throwaway compose stack. |
| `t10` | delivered | `tests.yml` jobs `web`, `image` (arm64) and `privacy`, plus the `changes` path filter. The GitHub runs have not happened yet because the branch is unpushed. |
| `t11` | delivered | Two cultureflare tunnels (`d1`), docs in `docs/remote-access.md`, live curl matrix. Zone cache bypass rules added for both hosts. |
| `t12` | delivered | Fork repo `agentculture/xteink-firmware` with `xteink-ci.yml` building every Xteink env. Green at `1c58a24b`. |
| `t13` | delivered | Pinned-root TLS in the shared downloader, OTA from fork releases, a services/TLS placement guard, and `scripts/xteink-tls/run.sh` (MITM refused). |
| `t14` | delivered | Zoom mode and reader menu, then reworked by `d2`, `d3`, `d5` and `d6` into the X3 key profile: tabs, hold-to-zoom, hold-to-rotate, paragraph scroll. |
| `t15` | delivered | Xteink theme (`src/components/themes/xteink/`), seen on the X3 by the operator. |
| `t16` | delivered | `XTEINK-PROV 1` serial provisioning. Used twice on the X3 (device ids 2 and 3). |
| `t17` | delivered | Sync client (protocol v1), device key in NVS, LAN first with tunnel fallback, home status line. Fixes E and F were added after hardware runs. |
| `t18` | delivered | `xteink device backup` and `xteink device provision` over esptool and USB serial. |
| `t19` | delivered | X3 probed (unlocked), 16 MB stock backup with sha256, first flash, provisioning (`docs/evidence/t19-x3-bringup.md`). |
| `t20` | partial | The real hardware runs covered MCP push to the X3 over hotspot and tunnel in 42.8 s, phone SSO upload to a LAN sync, offline reading, every key-profile function, and the c49 reboot. Still missing: a ≥ 5 MB EPUB over HTTPS (`o26`), a counted ≥ 10 pages in airplane mode (part of `o18`), and the restore rehearsal (part of `o29`). |
| `t21` | partial | README quickstart, `docs/api.md`, `docs/mcp.md`, `docs/remote-access.md` and `docs/device-protocol.md` landed. `CLAUDE.md` and the three other prompt files still say the firmware is "in progress, unverified … Do not claim that a device syncs end to end", which is now false. The fork's `docs/xteink/README.md` X3 row still says "hardware verification planned". |
| `t22` | delivered | `/validate-delivery` filed evidence `e1`–`e35` for 35 of the 36 obligations and behavioral deltas `b1`–`b8` (commit `0731153`). `o26` has no evidence. |
| `t23` | delivered | This file. |
| `t24` | blocked | Not started. It waits on this summary, the `t21` prompt-file fix and the history rewrite (below). |

## Mid-work Decisions

Approved deviations, quoted from the delivery store:

- `d1` — Two Cloudflare tunnels and two cloudflared services instead of one —
  cultureflare `ensure_tunnel_config` replaces a tunnel's whole ingress list,
  so two hostnames cannot share one tunnel; user chose two tunnels over
  blocking on a cultureflare change (2026-10-06).
- `d2` — Tabbed screens: Left/Right switch tabs, Up/Down move rows — user
  expectation stated during X3 hands-on (2026-10-06).
- `d3` — Reader line scroll on 4.3/4.4 — user request during X3 hands-on
  (2026-10-06). Superseded by `d6`.
- `d4` — The web UI on ebooks.culture.dev authenticates with Cloudflare Access
  SSO alone. API keys stay required for the device app, MCP and LAN API
  clients. Reason: the key panel was the agent's own interpretation of c77,
  shipped before the user answered.
- `d5` — X3 key profile from measured ADC values. The top regular button is
  the chip's hardware reset, so the edge keys page, hold 4.1 rotates, hold 4.2
  zooms, and a reset boots normally — user decisions after the key-logger
  session.
- `d6` — Reader scroll is by paragraph, not by line — operator request
  2026-10-07 after trying the d5 build.

Decisions no deviation record covers:

- **Rotate direction:** portrait goes to Landscape CCW (fork `1c58a24b`).
  This is the operator's preference after trying the first rotate build.
- **USB charging:** a top-key reset while charging over USB still
  charge-sleeps. The operator accepted it: "I can't read while it's on".
- **Wi-Fi auto-join (fix E):** 15 s per saved network within a 45 s budget,
  for risk `r25`. The extender needs 8.3 s, so auto-fallback failed at
  upstream's 7 s.
- **Free-space cache (fix F):** the SD free space is cached for sync reports,
  for risk `r21`. The 7 s free-space query was the slow step of a LAN sync.
- **App-only flashes:** firmware updates are written at 0x10000 only, after
  the factory image wiped the provisioned key (`l29`). The device was
  re-provisioned as device id 3, and ids 1 and 2 were revoked.
- **Zone cache:** bypass rules were added to the culture.dev zone for both
  hostnames, after its catch-all 2 h edge cache served a stale UI (`r24`,
  `l30`). This was an operator-approved Cloudflare change.
- **Redaction:** home network identifiers (extender SSID, BSSIDs, the saved
  password length) were removed from evidence and the fork checklist at the
  operator's request. The fork's public history keeps the SSID in `04b1e1fd`,
  which the operator accepted.

## Drift From Plan

| Plan item | Reason for divergence | Classification |
|-----------|-----------------------|----------------|
| `t11` (`d1`) | cultureflare `ensure_tunnel_config` replaces a tunnel's whole ingress list, so two hostnames cannot share one tunnel; user chose two tunnels over blocking on a cultureflare change (2026-10-06) | acceptable |
| `t14` (`d2`) | User expectation stated during X3 hands-on (2026-10-06): 'On settings, I expect left and right to move tabs, and up/down to move down the options on that tab' | needs-follow-up |
| `t14` (`d3`) | User request during X3 hands-on (2026-10-06): '4.3 move 1 line back, 4.4 move 1 line forward. Possible?' plus the 8-key layout description | needs-follow-up |
| `t7` (`d4`) | User (2026-10-06): 'I thought i only use sso? … I need an xtk api key' — the key panel was the agent's own interpretation of c77, flagged but shipped before the user answered | acceptable |
| `t14` (`d5`) | User decisions after the key-logger session: rotate wanted on the top button, which measured as a hardware reset; user chose long-press Back for rotate, long-press OK for zoom, and normal boot after reset | needs-follow-up |
| `t14` (`d6`) | Operator asked on 2026-10-07 after trying the d5 build: 'Can we change the next line, previous line to next paragraph, previous paragraph' | acceptable |
| `t17` | Fixes E (auto-join timeout) and F (free-space cache) were added after the hardware runs found `r25` and `r21`; no deviation record covers them | acceptable |
| `t20` | `o26` (≥ 5 MB EPUB over HTTPS), the counted ≥ 10 offline pages of `o18` and the restore rehearsal of `o29` were not run on hardware | needs-follow-up |
| `t21` | The prompt files' "current state" still marks the firmware unverified and forbids claiming an end-to-end sync, which the hardware evidence now contradicts | needs-follow-up |
| `t24` | Not started | needs-follow-up |

The `needs-follow-up` classification on `d2`, `d3` and `d5` comes from those
records. All three are now implemented and confirmed on the X3. What they
still need is the follow-up r2 names: re-measuring keys on other models.

## Evidence

Python suite and gates, at xteink `4eacfc2`:

- `uv run pytest -n auto --cov=xteink` — 444 passed, 2 skipped, coverage
  90.09%. The skips are host pandoc (it runs in the image) and a cross-repo
  report.
- black, isort, flake8, bandit, `teken cli doctor . --strict`,
  `scripts/scan-secrets.py` (263 files), `scripts/check-compose.sh`,
  `scripts/export-openapi.py --check`, `harness-smoke.py --stage config` (6
  passed) — all exit 0.
- `markdownlint-cli2` with the CI globs — 0 errors in tracked files. The only
  errors are in the untracked `.devague/reviews/` artifact.

Web:

- `web/`: vitest 63/63, `npm run typecheck` OK, `npm run build` OK.
- Playwright: 5/5 against the throwaway stack `xteink-e2e` built from
  `4eacfc2` (devices, library, send-to-device, settings, upload).

No-network runs:

- `.github/scripts/privacy-check.sh` (project `xteink-ci-val`): the negative
  control confirmed no outbound route. Then 281 core, server and MCP tests
  passed with no skips, the real-pandoc test passed, and a fake device synced
  2 items. Result: `PRIVACY OK`.
- The Python suite in a network namespace with only loopback up: 444 passed.

Fork, at `1c58a24b`:

- Host ctest 556/556. `scripts/xteink-check-services.py` OK. clang-format
  clean. `pio run -e default` OK. Local x4pro and x4c builds ran at
  `7f833be3`.
- GitHub Actions "Xteink CI" green at `1c58a24b`, `af5e7e1d`, `43676ff6`,
  `04b1e1fd`, `fd17732e` and earlier.
- `scripts/xteink-tls/run.sh` PASS: xteink.culture.dev VERIFIED; the MITM
  self-signed certificate, the wrong name and the unpinned root were each
  REFUSED.

Hardware and live evidence (`docs/evidence/`):

- `t11-remote-access-curl.txt`, `t19-x3-bringup.md`, `t20-first-sync.md`,
  `t20-phone-upload-lan-sync.md`, `d4-sso-web-ui.md`, `t20-zoom-mode.md`,
  `t20-paragraph-scroll.md`, `t20-x3-key-profile.md`, `c49-reboot.md`,
  `x3-key-mapping-serial.txt`.

devague records:

- evidence `e1`–`e35` and deltas `b1`–`b8` (filed `llm` origin, approved by
  the operator 2026-10-07); deviations `d1`–`d6` (approved); lapses
  `l1`–`l35` (all approved).

Commits and issues:

- xteink `main..0731153` (86 commits); fork `2f6a52c5..1c58a24b`.
- Issue `#1` (open). No PRs yet.

## Delivery Claims

Confidence follows the evidence. All lapses `l1`–`l35` are approved (the
operator confirmed `l3`–`l35` on 2026-10-07), so they count as evidence here.
Where a lapse bears on a claim, the claim names it.

| Claim | Confidence | Evidence |
|-------|------------|----------|
| `c2` — Four front doors (CLI, API, MCP, web UI) over one core, served on startup | high | test `tests/cli/test_nouns.py::test_cli_never_imports_core_or_server`, `tests/core/test_isolation.py` · evidence `e1` |
| `c3` — docker compose deployment that comes back after a host reboot | high | `docs/evidence/c49-reboot.md` · Playwright and privacy throwaway stacks · `e2`, `e19`. A literal fresh-clone run was not repeated (`l24` approved). |
| `c4` — ebooks.culture.dev behind SSO; xteink.culture.dev device-key only | high | `docs/evidence/t11-remote-access-curl.txt`, `docs/evidence/d4-sso-web-ui.md`, `docs/evidence/c49-reboot.md` · `e3` |
| `c5` — Our own themed firmware on the X3 | medium | operator observation, `docs/evidence/t19-x3-bringup.md` · `e4`. No screenshots (`l20` approved). |
| `c6` — Auto-joins the hotspot or home Wi-Fi; reads with Wi-Fi off | high | `docs/evidence/t20-first-sync.md`, `t20-x3-key-profile.md` ("Fallback works"), `t20-phone-upload-lan-sync.md` · `e5`, `b7`. Fix E has no unit test (`l35` approved). |
| `c7` — Button map, as amended by `d5`/`d6` | high | `docs/evidence/t20-x3-key-profile.md` (every row confirmed by the operator) · fork test `test/x3_key_profile` · `e6`, `b4`, `b6` |
| `c8` — Reader menu covers zoom and go-to | medium | zoom: `docs/evidence/t20-zoom-mode.md` · `e7`. Go-to exists in code only and was not exercised on the X3. |
| `c9` — Every Xteink model builds; X3 first | high (builds) / unverified (X4, X4 Pro, X4C on hardware) | fork Actions "Xteink CI" green at `1c58a24b` · `e8`. No other model was run on hardware (`r7`). |
| `c13` — xteink never handles `CLOUDFLARE_API_TOKEN` | high | test `tests/server/test_app_config.py::test_no_cloudflare_token_reads_in_package` · `e9` |
| `c17` — CLI is a thin API client with `--json`, explain and dry-run | high | `teken cli doctor --strict` PASS · `tests/cli/test_nouns.py` · `e10`. Its stubs were not captured from the live app (`l13` approved). |
| `c18` — Path-filtered web/image CI jobs | medium | local run of the web job's steps · `e11`. The GitHub web, image and changes jobs have not run (`l25` approved). |
| `c19` — No secrets in tracked files | high | `scripts/scan-secrets.py` clean · `tests/test_scan_secrets.py` · `e12` |
| `c21` — MCP tools over the same core | high | `tests/mcp/test_mcp_integration.py` (8) · production `push_file` in `docs/evidence/t20-first-sync.md` · `e13` |
| `c27` — Model differences behind HAL/build flags | medium | source review of the d5 diff (`HalGPIO::deviceIsX3`) · `e14` |
| `c28` — Sync on Wi-Fi join, sha256-verified, offline reading | high | `docs/evidence/t20-first-sync.md`, `t20-phone-upload-lan-sync.md` (`delivered_at` from verified acks) · `e15`, `b8` |
| `c33` — No unauthenticated service by default | medium | static guard `scripts/xteink-check-services.py` in CI · `e16`. No port scan of the X3. |
| `c47` — Operator flow: compose, web upload, book on the X3, read offline | high | `docs/evidence/t20-phone-upload-lan-sync.md`, `d4-sso-web-ui.md` · `e17` |
| `c48` — MCP push on the device ≤ 60 s after Wi-Fi join; pages with Wi-Fi off | medium | 42.8 s in `docs/evidence/t20-first-sync.md` · `e18`. The "≥ 10 pages" count was not made. |
| `c49` — Healthy ≤ 120 s after reboot, no manual step | high | `docs/evidence/c49-reboot.md` · `e19` |
| `c50` — Fork CI builds all envs; xteink CI green with coverage ≥ 60% | medium | fork CI green; xteink steps green locally (90.09%) · `e20`. xteink GitHub CI not run yet. |
| `c51` — 0 outbound connections with the tunnel off | high | `.github/scripts/privacy-check.sh` with its negative control · `e21` |
| `c52` — Tunnel is opt-in | high | `scripts/check-compose.sh` · `e22` |
| `c53` — Fork diff limited to theme/UI, input, Wi-Fi/sync, OTA, TLS | medium | diff review `2f6a52c5..1c58a24b` (89 files) · `e23`. Includes approved boot-path and reader changes (`d2`, `d3`/`d6`, `d5`). |
| `c55` — Versioned device protocol, same over LAN and tunnel | high | `tests/server/test_device_protocol.py` · both hardware paths · `e24` |
| `c56` — Five web UI flows verified by Playwright | high | `web/e2e/*.spec.ts` 5/5 · `e25` |
| `c61` — HTTPS sync within C3 RAM, for a ≥ 5 MB EPUB | unverified | (no evidence; only ~7 KB EPUBs were synced over TLS. Not claimed done.) |
| `c62` — Pinned-certificate verification, MITM fails closed | medium | `scripts/xteink-tls/run.sh` PASS (host wolfSSL, same flags and bundle) · device TLS sync in `t20-first-sync.md` · `e26`. MITM not run on the X3 (`l19` approved). |
| `c63` — OTA never offers upstream releases | medium | static guard rule "upstream OTA release feed" · `src/network/OtaUpdater.cpp` · `e27`. No on-device OTA check. |
| `c66` — Stock backup before the first flash; restore documented | medium | `docs/evidence/t19-x3-bringup.md` (sha256 verified) · `e28`. The restore was not rehearsed. |
| `c67` — Two cultureflare hostnames in front of the same origin | high | `docs/evidence/t11-remote-access-curl.txt` · `e29`, `b1` |
| `c70` — Zoom snaps to sizes, reflows once, keeps position | high | fork `test/zoom_mode` · `docs/evidence/t20-zoom-mode.md` · `e30` |
| `c72` — Mirror deletes, sd_full refusal, revocation | medium | `tests/server/test_device_protocol.py` · `e31`. Mirror delete and sd_full were not exercised on the X3. |
| `c73` — Per-device status in API/CLI/web; one-line device status | medium | `tests/core/test_devices.py`, `test_device_status_via_admin_api`, devices e2e · `e32`. The device status line was not checked on the X3. |
| `c74` — Upload containment on every path | medium | `tests/core/test_ingest.py`, `tests/server/test_app_routes.py::test_upload_too_large_413` · `e33`. Only the size limit is asserted at HTTP level. |
| `c81` — LAN/tailnet reachable with a key; tunnel routes only `/api/device/*` | medium | `t11-remote-access-curl.txt`, `c49-reboot.md`, `test_device_app_404_everywhere_else` · `e34`. A tailnet IP was not tested. |
| `c82` — Articles become EPUBs tagged article and read on the X3 | high | `tests/mcp/test_client.py::test_upload_markdown_is_article` · both device syncs · `e35` |

Lapse ledger: all 35 lapses are approved. How they bear on the claims above:

- **Cap a claim's confidence:**
  - `l20`: no panel screenshots of the theme, so `c5` is medium.
  - `l25`: the GitHub web, image and changes jobs haven't run, so `c18` is
    medium.
  - `l19`: TLS was measured on a host build, not on the C3, so `c62` is medium.
- **Noted but don't lower confidence**, because hardware or live evidence
  covers the claim directly:
  - `l24`: the fresh-clone build path, for `c3`; the reboot run covers it.
  - `l35`: fix E has no unit test, for `c6`; the operator confirmed the
    fallback.
  - `l13`: CLI test stubs, for `c17`; the CLI was used live for backup and
    provisioning, and `teken doctor` checks the real CLI.
- **Superseded by later evidence:**
  - `l6` and `l14`: the real pandoc test passes in the image.
  - `l26`: the sync client now has two hardware syncs.
  - `l12`, `l15` and `l34`: the x4pro and x4c builds are green in fork CI.
- **About this run's process, not the delivered behaviour:** `l1`, `l2`, `l3`,
  `l9`, `l10`, `l17`, `l18`, `l21`, `l22`, `l27`, `l29` and `l30`.
- **Assumptions still standing, carried into the follow-ups:**
  - `l4`: SQLite under concurrent threads.
  - `l5`: `rotate_key` re-enables a revoked device.
  - `l7`: ingest limits were chosen, not measured.
  - `l8`: Python 3.13 locally vs 3.12 in CI, and `serve()` is untested.
  - `l11`: socket-drop resume was only simulated.
  - `l16`: compose interpolation (fixed).
  - `l23`: MCP size field (fixed).
  - `l28`: the LAN probe root cause.
  - `l31`: battery thresholds for the reset boot.
  - `l32`: element yPos ordering for paragraph scroll.
  - `l33`: heap use while scrolling.

## Remaining Work / Follow-up

Blocking before the PRs:

- **`t21`:** update the "Current state vs. roadmap" in `CLAUDE.md`, `QWEN.md`,
  `AGENTS.colleague.md` and `AGENTS.override.md`/`.pi/SYSTEM.md`. The firmware
  is now hardware-verified on the X3, and the end-to-end sync is evidenced.
  Also update the fork's `docs/xteink/README.md` X3 row to "hardware-verified
  (docs/evidence in xteink)". Owner: main agent.
- **History rewrite:** before the first push of xteink `feat/issue-1`, strip
  the home SSID, BSSIDs and the saved-password length from the unpushed
  commits `45c1064`, `219da9d` and `9c6e989`, keeping a backup branch. Owner:
  main agent, with the operator's go-ahead.
- **`t24`:** minor version bump, `ask-colleague review` on both diffs, then
  PRs through `cicd` for xteink and the fork. The first GitHub CI run will
  cover `l25` (web, image and changes jobs). Close `#1` only when every
  success signal has passing evidence; today `c61` does not.
- **Adjudication:** done 2026-10-07. The operator confirmed evidence
  `e1`–`e35`, deltas `b1`–`b8` and lapses `l3`–`l35`.

Hardware checks still open:

- **`o26` / `c61`:** sync a ≥ 5 MB EPUB over HTTPS (hotspot or tunnel) on the
  X3 without OOM or a watchdog reset. Needs the operator and the X3.
- **`o18`:** count ≥ 10 pages read with Wi-Fi off.
- **`o29`:** rehearse the stock restore once (destructive; needs a reflash
  and re-provision afterwards). Could be deferred by an explicit decision.
- **`o16`, `o28`, `o33`, `o32`:** on-device checks still open: a port scan of
  the X3, an OTA check, a look at the home status line, and a mirror delete
  with sd_full on the device.

Follow-ups (plan risks, not blocking):

- `r26` more zoom sizes
- `r27` occasional double press on paragraph scroll
- `r28` injected secrets readable via `docker inspect`
- `r22` upstream TrustedTime double read (report upstream)
- `r23` LibraryList navigation
- `r19` the wheel serves the placeholder UI
- `r16` remaining `setInsecure` paths in the fork
- `r17` theme enum shift for X4 Pro/X4C users
- `r18` article titles come from the filename
- `r7` PDF ingest, remote MCP, culture-rules integration, other Xteink models
  on hardware
- `r21` and `r25` are addressed by fixes F and E and confirmed on the X3, but
  still open in the plan (a resolve is a plan move for the operator).
