# Build Plan — xteink end-to-end (issue 1)

slug: `xteink-end-to-end-issue-1` · status: `exported` · from frame: `xteink-end-to-end-issue-1`

> xteink ships end-to-end: one docker compose stack on spark serves the library API, MCP, CLI-backed management and a React web UI on startup, reachable at ebooks.culture.dev behind a key via cultureflare; Xteink readers (X3 first, all models) run our firmware that auto-joins a phone hotspot or home Wi-Fi, downloads books, and reads fully offline with a button-driven menu for pages and zoom

## Tasks

### t1 — Core library: storage, models and service layer (xteink/core/)

- instruction: Pure-stdlib core so the CLI stays dependency-free. Own files: xteink/core/\*\*, tests/core/\*\*, pyproject.toml (extra only). Keys are stored hashed (sha256) with a prefix id; never log raw keys.
- covers: c2, h2, c46, h20
- acceptance:
  - xteink/core/ provides a LibraryService (add, list, get, delete, search) and DeviceService (register, revoke key, queue, mark delivered, status) backed by stdlib sqlite3 + a files dir under a configurable `XTEINK_DATA_DIR`; tests in tests/core/ cover each operation
  - Items are deduplicated by sha256 and carry kind in {book, article}, title, author, format, size
  - pyproject.toml gains an optional extra 'server' (fastapi, uvicorn, mcp>=1.2,<2, python-multipart); base dependencies stay \[\] and 'import xteink.core' works with no extras installed
  - No network I/O anywhere in xteink/core (a test asserts socket is never opened during the core suite)

### t2 — Ingest: upload containment and Markdown/HTML to EPUB conversion (xteink/core/ingest.py)

- instruction: Mirror reterminal-cli reterminal/board/pdf.py containment style (size cap, magic bytes, timeout-bounded subprocess). Own files: xteink/core/ingest.py, tests/core/`test_ingest.py`, tests/fixtures/ingest/\*\*. Every upload path (web/API/MCP) must call this one function.
- depends on: t1
- covers: c74, h38, c82
- acceptance:
  - ingest() rejects oversized files, wrong magic bytes and an EPUB zip bomb (entry-count and uncompressed-size caps) with a typed IngestError; tests use fixtures for each
  - Markdown and HTML articles with title/author convert to EPUB via a timeout-bounded pandoc subprocess (shell=False) and are stored as kind=article; missing pandoc raises an environment error, not a traceback
  - EPUB, TXT and BMP pass through unchanged; PDF is rejected with a 'not supported yet' error (PDF conversion is a follow-up per c78)

### t3 — HTTP API: main app + device-only app, key auth (xteink/server/app.py, auth.py, `routes_library.py`)

- instruction: Two ASGI apps sharing the core: the device app is what xteink.culture.dev's tunnel points at, so tunnel exposure is limited by port, not by Cloudflare path rules (cultureflare has none). Ports 8000/8001/8770/8791 are taken on spark; 8780/8781 were free. Own files: xteink/server/{`__init__`,app,auth,`routes_library`,`routes_admin`}.py, tests/server/`test_app`\*.py, api/openapi.json, scripts/export-openapi.py.
- depends on: t1, t2
- covers: c81, h39, c13, h10
- acceptance:
  - FastAPI main app (default port 8780) exposes /api/library\*, /api/devices\*, /api/keys\* and serves packaged web assets at /; device-only app (default port 8781) exposes only /api/device/\* and returns 404 for every other path (test)
  - Every /api/\* route requires an API key (Authorization: Bearer) including on the LAN; device routes accept only device keys; revoked or missing keys -> 401 (tests)
  - Bind addresses are configurable (`XTEINK_BIND`, default 0.0.0.0 for LAN/tailnet); no xteink code reads `CLOUDFLARE_API_TOKEN` (grep test)
  - OpenAPI schema is exported to api/openapi.json by a script and checked in CI for drift

### t4 — Device protocol v1: endpoints + docs/device-protocol.md (xteink/server/`routes_device.py`)

- instruction: This doc is the contract the firmware fork implements; keep it versioned and small. Own files: xteink/server/`routes_device.py`, docs/device-protocol.md, tests/server/`test_device_protocol.py`, tests/server/`fake_device.py`.
- depends on: t3
- covers: c55, h28, c28, h16, c72, h36, c73, h37
- acceptance:
  - docs/device-protocol.md specifies v1: X-Xteink-Protocol header, device-key auth, GET queue (id, title, size, sha256, url), ranged GET download, POST ack with sha256, POST status (free SD bytes, firmware version, last error)
  - A fake-device client in tests/server/`fake_device.py` runs the full flow: queue -> download (incl. resumed range after a dropped connection) -> sha256 ack -> delivered; unknown protocol version -> 426 with a clear message
  - Insufficient free space reported by the device makes the queue omit oversized items with reason=`sd_full`; mirror-mode devices receive delete instructions only for unmodified delivered items; revoked key -> 401
  - Device status (`last_seen`, last sync result, queue) is readable via /api/devices/{id}

### t5 — MCP server with the official mcp SDK (xteink/mcp/)

- instruction: Follow culture-rules `culture_rules`/mcp/server.py patterns (mcp.types). MCP is LAN/tailnet/mesh only for issue 1 (c80): no tunnel route. Own files: xteink/mcp/\*\*, xteink/client.py, tests/mcp/\*\*.
- depends on: t3
- covers: c21, h14
- acceptance:
  - xteink/mcp/server.py (official mcp SDK) exposes `push_file`, `list_library`, `send_to_device` over stdio and streamable-http; each tool calls the HTTP API via xteink/client.py with an API key from env
  - An integration test drives the tools with the mcp SDK client against a test API: push a Markdown article -> listed as kind=article -> queued for a device; a missing/invalid key is refused
  - MCP holds no library logic (only API client calls); 'python -m xteink.mcp' starts it

### t6 — CLI nouns as thin API clients: server, library, device, tunnel, mcp (xteink/cli/`_commands`/)

- instruction: Register in `_build_parser` at the marked spot; copy the cli.py noun pattern. 'tunnel plan' prints the two cultureflare remote-login commands (dry-run) rather than calling Cloudflare. Own files: xteink/cli/`__init__.py`, xteink/cli/`_commands`/{server,library,device,tunnel,mcp}.py, xteink/explain/catalog.py, tests/cli/\*\*.
- depends on: t5
- covers: c17, h11
- acceptance:
  - New nouns server (status), library (add, list, rm), device (list, queue, revoke), tunnel (status, plan), mcp (serve) each have an overview verb, --json output and explain catalog entries; 'teken cli doctor . --strict' passes
  - Mutating verbs (library add/rm, device queue/revoke) print what they would do and change nothing without --apply (tests assert the API received no write)
  - CLI talks only to the HTTP API via xteink/client.py (stdlib urllib); no import of xteink.core or xteink.server from xteink/cli (test)

### t7 — Web UI: Vite + React + TS app with the five flows (web/)

- instruction: Load the frontend-design skill first and commit to a deliberate visual direction (e-ink inspired: paper tones, high contrast, serif reading type), not a template look. The LAN UI is open (c77); on the tunnel Cloudflare Access fronts it, so the UI must not assume a login screen. Own files: web/\*\* (including web/.gitignore) and xteink/server/`_webassets`/\*\* with its own .gitignore keeping only a placeholder; do not edit the root .gitignore (t8 owns it).
- depends on: t3, t4
- covers: c56
- acceptance:
  - web/ (Vite 6, React 18, TypeScript, vitest; mirrors reterminal-cli web/ layout) implements: upload (drag-drop, format check surfaced from ingest errors), library browse/search/delete, send-to-device with delivery status, devices (pair: show/QR device key once, last seen, revoke), settings (tunnel status, API keys)
  - Built assets land in xteink/server/`_webassets`/ and are served by the main app at /; vitest unit tests pass
  - UI calls only the HTTP API; no business logic in components beyond presentation

### t8 — Docker image + compose stack with remote profile (Dockerfile, compose.yaml, docker/)

- instruction: Ports 80/443 are free on spark but keep the app on 8780/8781 to avoid clashing with model-gear (8000/8001) and reterminal board (8770). Own files: Dockerfile, compose.yaml, .env.example, .dockerignore, docker/\*\*, .gitignore, scripts/check-compose.sh.
- depends on: t3, t5
- covers: c3, h3, c52, h26, c19, h13
- acceptance:
  - Multi-stage Dockerfile builds web assets then installs xteink\[server\] + pandoc for linux/arm64 (and amd64); compose.yaml runs api (8780 main, 8781 device) and mcp services with restart: unless-stopped and healthchecks; 'cp .env.example .env && docker compose up -d' works on a fresh clone
  - cloudflared runs only under '--profile remote' with `TUNNEL_TOKEN` from env; 'docker compose config' without the profile lists no cloudflared service (test script)
  - Library data persists on a named volume or `XTEINK_DATA_DIR` bind mount; .env, keys and data dirs are gitignored; only .env.example is tracked and scan-secrets.py stays clean
  - docker/avahi/xteink.service publishes xteink.local for host avahi with install notes (containers do not do mDNS)

### t9 — Playwright end-to-end flows against the compose stack (web/e2e/)

- instruction: Use the Playwright MCP tools available in-session for exploratory checks; the committed specs are the gate. Own files: web/e2e/\*\*, web/playwright.config.ts.
- depends on: t7, t8
- covers: h29
- acceptance:
  - web/e2e/ has one Playwright spec per flow (upload, library, send-to-device, devices, settings) that passes against 'docker compose up' with a seeded test key
  - Flows are also exercised once interactively via the Playwright MCP during development, with screenshots attached to the PR

### t10 — CI: web job, arm64 image build, egress-deny privacy test (.github/workflows/)

- instruction: Own files: .github/workflows/\*\*, .markdownlint-cli2.yaml. Keep jobs path-filtered so Python-only PRs stay fast.
- depends on: t8, t9
- covers: c18, h12, c51, h25, h24
- acceptance:
  - New path-filtered jobs: web (npm ci, build, vitest, Playwright on PRs touching web/\*\*), image (buildx linux/arm64 build), privacy (compose on an internal-only network; core/server tests + fake-device sync pass with 0 outbound connections)
  - Existing test/lint/harness-smoke/version-check jobs stay green; coverage `fail_under` stays >= 60; publish.yml paths unchanged unless web assets must ship in the wheel (then add web/\*\* and a build step)
  - markdownlint ignores web/`node_modules`; Actions pinned by SHA like the existing workflows

### t11 — Remote access via cultureflare: two hostnames, dry-run then apply (docs/remote-access.md)

- instruction: The --apply runs are outward-facing (DNS + Access on culture.dev): get explicit user go-ahead before each. xteink never calls the Cloudflare API itself. Own files: docs/remote-access.md.
- depends on: t8
- covers: c4, h4, c67, h34
- acceptance:
  - docs/remote-access.md gives the exact commands: 'cultureflare remote-login setup --hostname ebooks.culture.dev --service <http://127.0.0.1:8780> --allow `OWNER_EMAIL` --shushu' and '... --hostname xteink.culture.dev --service <http://127.0.0.1:8781> --no-access --shushu', dry-run output reviewed before --apply
  - After --apply (human-approved): anonymous <https://ebooks.culture.dev> -> Access login; <https://xteink.culture.dev/api/device/queue> without key -> 401, with device key -> 200; <https://xteink.culture.dev/api/library> -> 404 (curl transcript recorded)
  - `TUNNEL_TOKEN` is stored only in the shushu vault / .env, never in git

### t12 — Firmware fork repo + CI matrix for every Xteink env (agentculture/xteink-firmware)

- instruction: Creating the GitHub repo is outward-facing: get explicit user go-ahead and the exact repo name first. Do not modify upstream's reader engine (EPUB layout, fonts, SD, power) per c53.
- covers: c9, h9, c27, h15, c50, c53, h27
- acceptance:
  - Fork of crosspoint-reader/crosspoint-reader (develop) exists as an agentculture repo with upstream remote configured; README records per-model verification level (X3 hardware-verified, X4/X4Pro/X4C build-verified)
  - GitHub Actions matrix runs 'pio run' for every Xteink env (C3 default/X3 flag, x4pro, x4c) and passes; non-Xteink envs may stay but are not gated (c35)
  - CONTRIBUTING notes the allowed diff areas (theme/UI, input, Wi-Fi/sync config, sync client, OTA URL, TLS verification) and a script prints 'git diff --stat upstream/develop' for review

### t13 — Fork: security hardening - pinned TLS verification, no open services, OTA from fork releases

- instruction: Upstream already does verified HTTPS for OTA via wolfSSL (OtaUpdater.cpp:140-150); reuse that client config for sync instead of inventing a new TLS stack.
- depends on: t12
- covers: c62, h31, c63, h32, c33, h17, c61
- acceptance:
  - src/network/HttpDownloader.cpp no longer calls setInsecure(); requests verify against a pinned CA bundle for xteink.culture.dev; a MITM proxy with an untrusted cert fails closed (test/bench note)
  - File-transfer web server and the open 'CrossPoint-Reader' AP are off by default and only start from an explicit menu action
  - src/network/OtaUpdater.cpp points at the fork's GitHub releases; grep for the upstream releases URL returns nothing
  - All C3 envs still build with TLS enabled (wolfSSL path) in CI

### t14 — Fork: button map, zoom mode and reader menu (input + reader activities)

- instruction: Use MappedInputManager and the existing ButtonRemapActivity rather than raw GPIO; position by reading offset, not page number, because reflow renumbers pages.
- depends on: t12
- covers: c70, h35
- acceptance:
  - Left/Right = page back/forward; Confirm = Menu/OK; Back = Back/Cancel; the top key (verified on the X3, likely Up/Down in MappedInputManager) toggles zoom mode
  - In zoom mode an on-screen scale shows the available point sizes (built-in 12/14/16/18, vector 8-22); Left/Right step smaller/larger; leaving zoom mode reflows once and keeps the reading position (same passage on screen)
  - Reader menu offers go-to position/progress (percent/chapter) and zoom; on-device checklist in the fork's docs/test-x3.md

### t15 — Fork: xteink theme - boot, home and library screens designed for e-ink

- instruction: Load the frontend-design skill for direction, then translate to 1-bit/greyscale e-ink constraints; build on upstream's theme mechanism instead of patching renderers.
- depends on: t12
- acceptance:
  - Boot/splash, home and library screens use an xteink theme visibly distinct from stock CrossPoint themes (Classic/Lyra/RoundedRaff), registered as a selectable theme and default in our builds
  - Photo/screenshot of each screen on the X3 (792x528) attached to the fork PR

### t16 — Fork: serial provisioning handler (Wi-Fi networks, server URLs, device key)

- instruction: Document the serial message format in the fork's docs/provisioning.md; the xteink CLI (device provision) is the only intended client.
- depends on: t12
- acceptance:
  - Over USB serial the firmware accepts a versioned provisioning message: saved networks (stored in upstream's obfuscated /.crosspoint/wifi.json, max 8), LAN + tunnel server URLs, device key (stored in NVS); replies with device MAC and firmware version
  - Provisioning never echoes secrets back and is refused while not in an explicit provisioning screen

### t17 — Fork: xteink sync client (protocol v1), device key in NVS, LAN-first with tunnel fallback, status line

- instruction: Keep it a new module plus minimal hooks so upstream merges stay cheap (c53). Validate against the xteink fake-device tests' expectations, not ad-hoc behaviour.
- depends on: t12, t4, t13
- covers: c28, h16, c55, c73
- acceptance:
  - New sync module implements docs/device-protocol.md v1 from the xteink repo: queue fetch, ranged download to microSD, sha256 verify, ack, status report (free SD, firmware version, last error)
  - Server order (decision c60): provisioned LAN URL / xteink.local first, then <https://xteink.culture.dev> with verified TLS; device key read from NVS and sent only same-origin
  - Home screen shows a one-line sync status (ok / n new / error code); sync runs on Wi-Fi join and from a menu action; reading never waits on the network

### t18 — CLI: device backup and device provision over USB (xteink/cli/`_commands`/`device_usb.py`)

- instruction: Mirror reterminal-cli reterminal/cli/`_commands`/firmware.py's esptool shell-out (--esptool 'uvx esptool@latest' override). Wi-Fi passwords come from a gitignored local file or prompt, never argv history. Own files: xteink/cli/`_commands`/`device_usb.py`, tests/cli/`test_device_usb.py`, plus a registration line and catalog entries.
- depends on: t6, t16
- covers: c66, h33
- acceptance:
  - 'xteink device backup --port /dev/ttyACM0 \[--apply\]' shells out to esptool (read-flash full size, external tool, not a dependency) and stores the dump + sha256 under the data dir keyed by MAC; dry-run prints the command
  - 'xteink device provision --port ... \[--apply\]' mints a device key via the API, sends networks/server URLs/key per the fork's provisioning format, and prints only the key id, never the key
  - Both verbs have explain entries, --json, and tests with a fake serial port / fake esptool

### t19 — X3 bring-up: probe, stock backup, first flash, provisioning (hardware, MAC 68:C6:3A:3B:C2:4C)

- instruction: Hardware task: needs the user present to wake/hold buttons. Flashing is hard to reverse; confirm with the user right before write-flash.
- depends on: t18, t13, t14, t15, t17
- acceptance:
  - esptool get-security-info result recorded (USB-locked or not); if locked, switch to the SD update.bin route and record the deviation via /deviate
  - Full stock flash backup exists with sha256 before the first flash; restore procedure rehearsed or documented with crosspoint-tools boot repair
  - Fork firmware flashed, device provisioned with home LAN + 'iPhone (5)' and a device key; boots to the xteink theme

### t20 — Hardware end-to-end validation on the X3 and spark (evidence run)

- instruction: Record raw timings, transcripts and photos; these become /validate-delivery evidence. A failed measurement is recorded as failed, never re-run until it passes silently.
- depends on: t19, t11, t9
- covers: c48, h22, c6, h6, h30, h40, c49, h23, c5, h5, c7, h7, c8, h8
- acceptance:
  - MCP `push_file` of a book and of a Markdown article -> on the X3 within 60 s of Wi-Fi join (home LAN and iPhone hotspot runs, timings recorded); >= 10 pages read in airplane mode
  - A >= 5 MB EPUB downloads over the hotspot via xteink.culture.dev without reset; button map, zoom mode and menu checklist pass (photos)
  - spark reboot: all services healthy <= 120 s, anon tunnel requests -> SSO / 401 (transcript)

### t21 — Docs and prompt files: README quickstart, MCP/API docs, CLAUDE.md current state, harness prompts

- instruction: Someone other than the author should be able to follow the README end to end (h21); verify by a fresh-clone run. Own files: README.md, docs/mcp.md, docs/api.md, CLAUDE.md, QWEN.md, AGENTS.colleague.md, .pi/SYSTEM.md.
- depends on: t6, t8, t11
- covers: c44, h18, c45, h19, c47, h21
- acceptance:
  - README quickstart (compose up, upload, provision a device) and docs/mcp.md + docs/api.md (keys, endpoints) exist and pass markdownlint
  - CLAUDE.md 'Current state vs. roadmap' moves landed items out of (planned); QWEN.md, AGENTS.colleague.md and .pi/SYSTEM.md get the same project facts (harness-smoke stays green)
  - Before-state evidence: 'git ls-files' at the spec commit bd4f04a shows no server/API/MCP/web/firmware code (recorded in the PR)

### t22 — /validate-delivery: run behavioral tests and file evidence for o1-o36

- instruction: Run the /validate-delivery skill after all build waves merge and before /summarize-delivery.
- depends on: t10, t20, t21
- covers: c1, h1
- acceptance:
  - Every obligation o1-o36 has an evidence record (pass or fail, with test ref and run commit) filed via devague evidence; failures filed as failures
  - Behavioral deltas the run added/amended are filed via devague delta

### t23 — /summarize-delivery: planned vs actual accountability artifact

- instruction: Run on complete, partial or failed runs alike; report faithfully.
- depends on: t22
- acceptance:
  - devague summary + /summarize-delivery produce the delivery summary (planned vs actual, deviations, evidence-backed claims, remaining work incl. PDF conversion and remote MCP follow-ups)

### t24 — Version bump, ask-colleague review and PRs via cicd (xteink + fork)

- instruction: PR body links the spec, plan, delivery summary and closes #1 only if every success signal has passing evidence; otherwise it references #1.
- depends on: t23
- acceptance:
  - xteink: version bumped (minor) with CHANGELOG, ask-colleague review run on the diff, PR opened via the cicd skill and CI + SonarCloud green; fork: PR/release with the same summary

## Risks

- [unknown_nonblocking] X3 USB lock status unknown (frame v1): if get-security-info shows a locked unit, flashing moves to the SD update.bin route and USB provisioning (t18) may need an SD-file fallback (task t19)
- [unknown_nonblocking] Exact X3 top-key set unverified (frame v2): the zoom toggle binding in t14 is finalized only after an on-device button probe (task t14)
- [unknown_nonblocking] Creating the agentculture firmware fork repo needs the user's go-ahead and org permissions; every firmware task waits on it (task t12)
- [unknown_nonblocking] Fork tasks t13-t16 share a wave and may touch the same upstream files (SettingsList.h, main.cpp, activity registration); merge them sequentially in the fork and rebase, rather than in parallel (task t13)
- [unknown_nonblocking] Real sync time and battery cost per sync on the X3 unmeasured (frame v4); the 60 s target may need a recorded deviation after t20 (task t20)
- [unknown_nonblocking] Upstream CrossPoint moves fast; merge cost unknown until the first upstream sync (frame v5) (task t12)
- [follow_up] Follow-ups outside issue 1: PDF conversion (c78), remote MCP/API (c80), culture-rules push integration (c22), X4/X4Pro/X4C hardware verification
