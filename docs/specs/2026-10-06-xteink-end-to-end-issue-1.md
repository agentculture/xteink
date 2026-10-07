# xteink end-to-end (issue 1)

> xteink ships end-to-end: one docker compose stack on spark serves the library API, MCP, CLI-backed management and a React web UI on startup, reachable at ebooks.culture.dev behind a key via cultureflare; Xteink readers (X3 first, all models) run our firmware that auto-joins a phone hotspot or home Wi-Fi, downloads books, and reads fully offline with a button-driven menu for pages and zoom
> instruction: spec-to-plan maps each announcement clause to a task with acceptance criteria

## Audience

- The operator (a single household/owner) reading on Xteink readers, plus agents and code (culture-rules, Claude via MCP) that push documents to the library
  - instruction: docs review

## Before → After

- Before: Books reach an Xteink only through the vendor's stock firmware/app or manual SD-card copying; there is no private server, no agent push path, and xteink itself is only an agent scaffold (no server, API, MCP, web UI or firmware)
  - instruction: git ls-files at spec commit
- After: After 'docker compose up -d' on spark, the library is browsable and uploadable at <http://localhost> and <https://ebooks.culture.dev> (behind SSO); a book pushed by CLI, web UI or MCP shows up on the X3 at its next Wi-Fi join (home LAN or the 'iPhone (5)' hotspot) and stays readable with Wi-Fi off
  - instruction: follow README on a clean checkout

## Why it matters

- Privacy is the product: the library and reading data stay on hardware the owner controls, while agents can still deliver generated documents to a reader that works with zero network
  - instruction: egress test c51

## Requirements

- Four front doors over one core: CLI, HTTP API, MCP server, and a React web UI (flows for upload/library/device), all served on startup
  - instruction: grep-level check: xteink/cli and xteink/mcp import only the API client; API contract tests cover each operation once
  - honesty: CLI, MCP and web UI contain no library/business logic of their own: all go through one service layer exposed by the HTTP API
- Deployment is docker compose (preferred), auto-started on host boot (restart: unless-stopped)
  - instruction: CI builds images for arm64 (buildx); compose config lint; reboot test in c49
  - honesty: A fresh clone runs with 'cp .env.example .env && docker compose up -d' on linux/arm64, and every service has restart: unless-stopped and a healthcheck
- Public access via cultureflare: <https://ebooks.culture.dev> (web UI, Cloudflare Access SSO) and <https://xteink.culture.dev> (device endpoint, xteink device key)
  - instruction: curl matrix: anon browser -> Access login; /api without key -> 401; with key -> 200
  - honesty: ebooks.culture.dev is provisioned only via 'cultureflare remote-login setup' and never serves the web UI without an Access session or /api/\* without a valid key
- Our own firmware on the reader, designed to look good (custom UI, not stock)
  - instruction: photo/screenshot evidence of the boot + library screens on the X3
  - honesty: The reader boots our fork (custom theme/splash/boot screen visibly distinct from stock CrossPoint) on the X3
- Device Wi-Fi auto-connects to a known iPhone hotspot and to the home LAN, whichever is available, to download books; reading then works with Wi-Fi off
  - instruction: hardware run: home LAN only, hotspot only, neither -> reading works
  - honesty: With both networks saved, the device joins whichever is in range without user action; with neither, it does not block reading
- Button map: left/right = previous/next page (or zoom -/+ while zoom mode is on, per c40); bottom keys = Menu/OK and Back/Cancel; top key = zoom-mode toggle
  - instruction: on-device test checklist in the fork repo, executed on the X3
  - honesty: Left/right page, Menu/OK and Back/Cancel work as specified on the X3; top button toggles zoom mode per c40
- On-device menu covers zoom (font size) and page navigation (go-to page / progress)
  - instruction: on-device checklist + photo evidence
  - honesty: Menu offers go-to-page/progress and zoom; zoom scale is visible while zoom mode is on and right increases text size
- Support all Xteink models; X3 is the first target since it is the unit on hand
  - instruction: fork CI matrix; mark per-model verification level in the fork README
  - honesty: Every Xteink firmware env builds in CI; X3 is hardware-verified; other models are build-verified until a unit is available
- The CLI is a thin client of the HTTP API (server lifecycle, library add/list/rm, device list/queue, tunnel up/down), with --json, explain-catalog entries per verb, and write verbs dry-run by default with --apply
  - instruction: teken cli doctor --strict passes; tests assert dry-run makes no changes
  - honesty: Every new verb has --json, an explain entry, and mutating verbs refuse to change state without --apply
- New top-level web/ (Vite+React+TS, mirroring reterminal-cli web/) and docker/ compose assets get path-filtered CI jobs in this repo (publish.yml only triggers on pyproject.toml and xteink/\*\*); firmware CI lives in the fork repo
  - instruction: workflow job + a test that the server serves index.html from packaged assets
  - honesty: web/ build and tests run in CI on PRs touching web/\*\*; the wheel/image includes the built assets
- MCP server exposes `push_file` / `list_library` / `send_to_device` (queue for device) over the same core as the API; culture-rules calls it via MCP or a CodeRunner argv step (xteink library add ... --apply)
  - instruction: MCP integration test using the official mcp SDK client over stdio/streamable-http
  - honesty: An MCP client (Claude Code) can `push_file`, `list_library` and `send_to_device` against the running stack, authenticated with an API key
- Model matrix from upstream platformio.ini: X3/X4 share the esp32-c3 env (X3 via -`DFREEINK_DEVICE_X3`=1), X4Pro and X4C have esp32-s3 envs; our fork keeps every upstream env building in CI so 'all versions' is a CI-checked claim
  - instruction: pio run for each env in CI
  - honesty: The fork keeps all upstream Xteink envs and adds no model-specific code paths without a HAL flag
- Device sync pulls from the xteink server (OPDS feed and/or a small JSON 'queue' endpoint) on Wi-Fi join; books land on the microSD and reading never touches the network
  - instruction: fake-device contract tests incl. dropped-connection case
  - honesty: A queued book is fully on microSD and sha256-verified before the device ACKs, and an interrupted download resumes or retries without corrupting the library
- Device sync contract (versioned, documented in docs/device-protocol.md): device authenticates with a per-device key, GETs its queue (book id, title, size, sha256, url), downloads each to microSD, verifies sha256, ACKs; server marks delivered. Works identically over LAN IP and ebooks.culture.dev
  - instruction: contract test for version mismatch
  - honesty: Protocol is versioned and the server rejects unknown versions with a clear error
- Web UI flows: (1) upload by drag-drop with format check, (2) library browse/search/delete, (3) send-to-device queue with delivery status, (4) devices: pair (show device key/QR), last seen, (5) settings: tunnel status and API keys. Designed with frontend-design, verified by Playwright flows
  - instruction: playwright test suite in CI
  - honesty: Each flow has a passing Playwright test against the compose stack
- Firmware sync client supports HTTPS (TLS) to xteink.culture.dev within ESP32-C3 RAM limits (no PSRAM on X3/X4), since the hotspot fallback goes through the tunnel; upstream already runs TLS on C3 via wolfSSL
  - instruction: fork CI builds C3 envs with TLS enabled; hardware run downloads a >=5 MB EPUB over the hotspot
  - honesty: A >=5 MB EPUB downloads over TLS on the X3 without OOM or watchdog reset
- Firmware verifies the server certificate on every HTTPS sync: replace upstream's http.setInsecure() (src/network/HttpDownloader.cpp:36) with a pinned CA bundle for xteink.culture.dev's Cloudflare edge chain, so the device key cannot be MITM'd on a hotspot
  - instruction: fork test: sync against a self-signed MITM proxy fails closed; against ebooks.culture.dev succeeds
  - honesty: No code path in the fork's sync client calls setInsecure()
- Fork repoints OTA (upstream src/network/OtaUpdater.cpp:22 hardcodes api.github.com/repos/crosspoint-reader/crosspoint-reader/releases/latest) to the fork's own releases, or disables it, so an on-device 'update' never silently replaces our firmware with stock CrossPoint
  - instruction: grep the fork for the upstream releases URL returns nothing; OTA from fork releases tested once on the X3
  - honesty: An OTA check on the X3 running our fork never offers an upstream CrossPoint build
- Before the first flash of any unit, 'xteink device backup --port ... --apply' dumps the full stock flash (esptool read-flash) to the server's private store, and docs give the restore path (esptool write-flash / crosspoint-tools boot repair)
  - instruction: backup file exists with sha256 for MAC 68:C6:3A:3B:C2:4C before first flash; restore rehearsed once
  - honesty: A restorable full-flash backup exists for every unit before it is first flashed
- Remote access uses two cultureflare hostnames: `remote-login setup --hostname ebooks.culture.dev --allow OWNER_EMAIL` (Access SSO, web UI) and `remote-login setup --hostname xteink.culture.dev --no-access` (device endpoints; xteink enforces the device key), both in front of the same origin
  - instruction: curl matrix after both setups: anon <https://ebooks.culture.dev> -> Access login; <https://xteink.culture.dev/api/device/queue> without key -> 401, with key -> 200; any other path via xteink.culture.dev -> 404
  - honesty: Anonymous requests to the UI get SSO while key-authenticated /api/device/\* requests are admitted without SSO, verified by curl
- Zoom = reader font point size: built-in fonts offer 12/14/16/18 pt, vector fonts 8-22 pt (upstream src/ReaderFontSizes.h). The zoom scale shows these steps; re-layout happens once when zoom mode exits (not per press), and position/progress is kept by reading position (percent/chapter offset), not page number, since reflow renumbers pages
  - instruction: on-device: toggle zoom, step 3x right, exit -> same passage stays on screen; go-to-page reflects new pagination
  - honesty: Changing zoom never loses the reader's place in the book
- Lifecycle: removing a book from the server's device queue/library removes it from the device on next sync only if the device-side copy is unmodified (opt-in 'mirror' per device); low-SD-space is reported to the server and blocks the download instead of failing mid-write; a lost device's key is revocable from CLI/web
  - instruction: contract tests: delete propagation, insufficient-space response, revoked key -> 401
  - honesty: Device-side deletes only remove unmodified copies the server delivered, never user-sideloaded files
- Observability: the server records per-device `last_seen`, last sync result and queue state (visible in web UI and 'xteink device list --json'); the device shows a one-line sync status (ok / n new / error code) on the home screen
  - instruction: API test for device status fields; on-device photo of status line
  - honesty: After each sync the server's device status matches what is actually on the device
- Upload containment: size cap, magic-byte/format check, EPUB zip-bomb guard (max entries/uncompressed size), timeout-bounded conversion subprocesses; applies equally to web, API and MCP uploads
  - instruction: tests with an oversized file, wrong magic bytes and a zip bomb all rejected with 4xx
  - honesty: Every upload path (web, API, MCP) runs the same containment checks
- The API/MCP listener is reachable from the LAN and the Tailscale/mesh interfaces of spark (not just 127.0.0.1), while the tunnel ingress for xteink.culture.dev routes only /api/device/\* to the origin; any other path through the tunnel returns 404
  - instruction: curl via tailnet IP with key -> 200; curl <https://xteink.culture.dev/api/library> with key -> 404
  - honesty: No library-write or MCP endpoint is reachable through either Cloudflare hostname
- Articles are first-class: `push_file` / web upload accept Markdown and HTML articles (with title/author metadata) and convert them to EPUB (c78), listed alongside books with a kind=article tag
  - instruction: MCP test pushes a Markdown article -> EPUB appears in library with kind=article and syncs to the device
  - honesty: A converted article opens and paginates on the X3 like any EPUB

## Honesty conditions

- Every surface in the announcement exists and is exercised by at least one automated or recorded test
- No `CLOUDFLARE_API_TOKEN` or tunnel credential is ever read by xteink code or committed; cloudflared gets `TUNNEL_TOKEN` only from env/vault
- Tracked tree contains only \*.example config; real .env, secrets and device keys are gitignored
- Our firmware never starts an unauthenticated HTTP server or open AP by default
- Both audiences have a documented entry point: README quickstart for humans, MCP/API docs for agents
- The before state is accurate for this repo: no server/API/MCP/web/firmware code exists on main at spec time
- No book or reading data leaves owned hardware except over the opt-in tunnel to the owner's own clients
- The after state is reproducible from docs alone by someone other than the author
- The measurement is taken on the real X3, not an emulator
- The reboot test is actually performed on spark
- Coverage gate stays at `fail_under`=60 or higher
- The egress test runs in CI, not only manually
- Without the remote profile, docker compose up starts no cloudflared container
- Diff of the fork vs upstream is confined to theme/UI, input, Wi-Fi config and sync modules

## Success signals

- End-to-end on the real X3: a book uploaded via MCP `push_file` appears on the device within 60 s of the device joining Wi-Fi, and opens and pages with Wi-Fi off
  - instruction: evidence includes device serial 68:C6:3A:3B:C2:4C
- After a host reboot, all compose services (api+web, mcp, cloudflared) are healthy within 120 s with no manual step, and <https://ebooks.culture.dev> returns the SSO wall for an anonymous browser and 401 for an API call without a key
  - instruction: record ps/curl output after reboot
- CI builds every Xteink firmware env (X3/X4 C3, X4Pro, X4C) in the fork repo, and the xteink repo's test, web and lint jobs pass with coverage >= 60%
  - instruction: pyproject coverage config unchanged or raised
- Privacy: with the tunnel off, the stack makes 0 outbound connections other than to the device LAN (no telemetry), verified by a network-namespace/egress test
  - instruction: CI job with an internal-only docker network

## Scope / boundaries

- Tunnel creation, DNS, Access apps and service tokens are owned by cultureflare; xteink only runs the cloudflared connector (compose service) with the sealed tunnel token and never handles `CLOUDFLARE_API_TOKEN`
  - instruction: scan-secrets clean; grep xteink/ for `CLOUDFLARE_API_TOKEN` returns nothing
- No secrets in tracked files: Wi-Fi SSIDs/passwords, tunnel token and API keys live in gitignored .env / secrets.h with tracked \*.example files; scan-secrets.py flags token/password literals >=20 chars and non-localhost url keys in JSON
  - instruction: scan-secrets.py clean in CI; .gitignore covers .env, secrets.h, \*.key
- Firmware never exposes an unauthenticated network service by default: upstream CrossPoint's file-transfer web server (ports 80/81, no auth) and open 'CrossPoint-Reader' AP must be off or gated in our build
  - instruction: fork test/config check; port scan of the device on LAN shows nothing listening unless explicitly enabled
- Tunnel is opt-in: compose profile 'remote' runs cloudflared; without it nothing is reachable from outside the LAN
  - instruction: docker compose config --profiles; ps shows no cloudflared
- Firmware fork keeps upstream CrossPoint's reader engine (EPUB layout, fonts, SD, power) untouched where possible; our changes are theme/UI, button map/zoom, saved-network config and the xteink sync client, to keep upstream merges cheap
  - instruction: git diff --stat upstream/master in the fork

## Non-goals

- No changes to culture-rules in this issue: it has no outbound MCP/HTTP plugin point (actors/code.py CodeRunner, urllib actors), so integration is a follow-up there
- Not targeting non-Xteink CrossPoint devices (reTerminal Sticky, M5PaperMono) even though the fork inherits their envs
- No user accounts / multi-tenant library, no DRM'd store integration, no Calibre replacement, no KOReader progress server in issue 1

## Assumptions

- Host is spark-f8a9 (aarch64, DGX Spark) with Docker 29.1.3 + Compose v5.0.1, cloudflared, node/npm already installed, so the compose images must build for linux/arm64
- cultureflare `remote-login setup --hostname HOST --service http://127.0.0.1:PORT [--no-access | --allow EMAIL --with-service-token] --shushu` provisions tunnel+DNS(+Access) dry-run-first; xteink cites this command rather than reimplementing Cloudflare API calls
- Web UI is designed with the frontend-design skill and verified end-to-end with the Playwright MCP (browser flows), which are available in this environment
- .gitignore lacks `node_modules`/, web build output and docker/.env, and markdownlint must ignore web/`node_modules`, so web/compose scaffolding adjusts .gitignore and markdownlint ignores (firmware dirs live in the fork repo, so the lib/ ignore at .gitignore:17 is moot here)
- Document conversion (PDF/Markdown/HTML -> device format) can reuse reterminal-cli board/pdf.py containment pattern (size cap, magic bytes, timeout-bounded subprocess, rasterize once and cache)
- X3 panel is 792x528 SSD1677, no touch/frontlight, has gyro + 16GB microSD (pocketink.io/devices/x3, third-party source, unverified against the unit)
- ESP32-C3 is 2.4 GHz only, so the iPhone hotspot needs 'Maximize Compatibility' enabled; 'iPhone (5)' is read as a hotspot SSID, not an iPhone 5 handset (unverified, needs user confirmation)
- The X3 is physically on spark: kernel log 20:03:01 shows Espressif 'USB JTAG/serial debug unit' (ESP32-C3 native USB) as ttyACM0, MAC 68:C6:3A:3B:C2:4C, then disconnect at 20:03:02, so the data cable works and the native USB is exposed but drops when the reader sleeps; lock status still unverified (needs esptool `chip_id`/`read_mac` with the device awake)
- Counter-evidence to earlier reasoning: upstream firmware already sends custom headers on same-origin requests (HttpDownloader.cpp, caller headers + basic auth) and already does TLS on ESP32-C3 via wolfSSL for OTA (OtaUpdater.cpp:144), so sending a device key header is easy and the TLS-RAM risk (v3) is smaller than assumed
- Upstream stores Wi-Fi credentials on the microSD at /.crosspoint/wifi.json, passwords obfuscated with a hardware-derived key (src/WifiCredentialStore.h/.cpp:17), max 8 networks
- On spark, ports 80/443 are free but 8000, 8001, 8770 (reterminal board), 8791 and others are taken; avahi-daemon is active on the host, so xteink.local must be published by host avahi (a service file), not from a bridge-network container

## Scope exploration

- `s1` — `host spark-f8a9 (docker/compose/cloudflared/node, uname -m)`: aarch64 host already has Docker 29.1.3, Compose v5.0.1, cloudflared, node/npm; compose images must target linux/arm64
  - seeds: `c10`, `c3`
- `s2` — `host USB bus (lsusb, /dev/ttyACM*, /dev/serial/by-id)`: point-in-time lsusb showed no device, but kernel log shows the X3 enumerating briefly as ttyACM0 then dropping (see s20); it is connected but only visible while awake
  - seeds: `c11` (rejected)
- `s3` — `xteink issue #1 (guildmaster build brief)`: brief asks for server+tunnel+CLI+shared API+MCP+device software; prefers stock CrossPoint (option a) over fork/new firmware; names culture-rules as MCP consumer; requires write verbs dry-run by default with --apply; remote access off by default
  - seeds: `c2`, `c5`
- `s4` — `cultureflare README.md:50-66 + cli/_commands/remote_login.py`: remote-login setup provisions tunnel+CNAME+ingress, optional Access app/service token; --no-access mode requires the backend to enforce its own auth (README security note); --shushu seals `tunnel_token` into the vault
  - seeds: `c12`, `c13`
- `s5` — `cultureflare _remote_login/_access_policy.py:95-102; ~/.cloudflared, /etc/cloudflared`: service-token headers are 302'd to SSO unless a `non_identity` policy exists, so device firmware would need to send CF-Access headers; no existing tunnel config on disk for this host
  - seeds: `c14` (rejected)
- `s6` — `user message: frontend-design + playwright MCP`: frontend-design skill and Playwright MCP tools are available in-session for the React UI design and flow verification
  - seeds: `c15`
- `s7` — `xteink pyproject.toml:16 + CLAUDE.md 'The CLI'`: runtime dependencies = \[\] by convention; server/MCP deps need an optional extra or deliberate change; hatch wheel ships only xteink/
  - seeds: `c16`
- `s8` — `xteink/cli/__init__.py:64-95 + _commands/cli.py:30-43 + explain/catalog.py`: new noun groups register in `_build_parser` (marked spot :91-93), need an overview verb, explain-catalog entries, and teken cli doctor --strict; no --apply convention exists yet
  - seeds: `c17`
- `s9` — `.github/workflows/tests.yml + publish.yml:5-14`: CI is Python-only (node only for markdownlint); publish triggers on pyproject.toml and xteink/\*\* only; web/ and firmware/ need new path-filtered jobs; version-check still requires a bump
  - seeds: `c18`
- `s10` — `scripts/scan-secrets.py:51-79,179-220`: flags token/password/secret literals >=20 chars in any tracked file and non-localhost http(s) under url/host keys in JSON; `${VAR}` and `<placeholder>` values are exempt
  - seeds: `c19`
- `s11` — `.gitignore:17 + .markdownlint-cli2.yaml`: lib/ is ignored (would hide firmware/lib); `node_modules`/.pio/secrets.h/\*.bin not ignored; markdownlint lints every .md so web/firmware READMEs must pass
  - seeds: `c20`
- `s12` — `culture-rules actors/code.py:148-172, mcp/server.py:28, deploy/cloudflared/`: no outbound MCP/HTTP plugin point; integration path is a CodeRunner argv step or a urllib actor; culture-rules uses official mcp SDK and a systemd cloudflared unit with grant-injected `TUNNEL_TOKEN`
  - seeds: `c21`, `c22`, `c24` (rejected)
- `s13` — `reterminal-cli board/pdf.py, web/package.json, deployments/systemd/`: closest prior art: stdlib board server, PDF rasterize-once cache with containment, Vite6/React18/TS web built into package assets, cloudflared via systemd (no compose)
  - seeds: `c23`, `c18`
- `s14` — `reachy-mini-mcp/pyproject.toml:27`: FastMCP precedent (fastmcp>=0.1.0, stdio serve)
  - seeds: `c24` (rejected)
- `s15` — `xteink template leftovers (cli/__init__.py:74, learn.py:15, catalog.py:15/84, overview.py:4, doctor.py:7/40, whoami.py:7)`: still describe a clonable template; touched by any new CLI work
  - seeds: `c25` (rejected)
- `s16` — `daveallie/crosspoint-reader platformio.ini + README.md (fetched)`: MIT, PlatformIO; esp32-c3 envs default/`gh_release`/slim with -`DFREEINK_DEVICE_X3`=1; esp32-s3 envs x4pro/x4c/sticky; README lists X3/X4 (C3) and X4Pro/X4Classic (S3), themes, button remapping, tilt page turn on X3
  - seeds: `c26`, `c27`, `c35`
- `s17` — `crosspoint docs/webserver.md + pocketink.io flash guide (subagent web research)`: STA tries last-used then saved networks by RSSI; file-transfer server on 80/81 has no auth; open AP 'CrossPoint-Reader'; some 2026 X3/X4 units are USB-locked (SD update.bin / OTA Unlocker routes); bootloop risk recoverable via crosspoint-tools repair
  - seeds: `c28`, `c30` (rejected), `c33`
- `s18` — `pocketink.io/devices/x3 + circuitpython.org xteink_x4 pinouts`: X3: ESP32-C3, 792x528 SSD1677, gyro, microSD; X4: 7 buttons via ADC ladder (power GPIO3); X3 button layout differs from X4 and is unverified
  - seeds: `c29`, `c32` (rejected)
- `s19` — `ESP32-C3 radio / iPhone Personal Hotspot`: 2.4 GHz only; iPhone hotspot needs Maximize Compatibility; hotspot sleeps without clients (agent knowledge, unverified in-session)
  - seeds: `c31`
- `s20` — `journalctl -k (spark-f8a9, last 30 min)`: X3 enumerated as Espressif USB JTAG/serial (ESP32-C3) ttyACM0 MAC 68:C6:3A:3B:C2:4C, disconnected ~1s later; supersedes the earlier 'not visible' finding from a point-in-time lsusb
  - seeds: `c39`, `c30` (rejected)
- `s21` — `challenge pass / security lens: crosspoint src/network/HttpDownloader.cpp:36`: upstream HTTPS downloads call setInsecure() (no cert validation); unacceptable once a device key rides the tunnel path over a hotspot
  - seeds: `c62`
- `s22` — `challenge pass / lifecycle lens: crosspoint src/network/OtaUpdater.cpp:22`: built-in OTA pulls upstream GitHub releases; unchanged, it would revert the device to stock
  - seeds: `c63`
- `s23` — `challenge pass / counter-evidence lens: crosspoint HttpDownloader.cpp + OtaUpdater.cpp:140-150`: the 'firmware cannot send CF-Access headers' premise behind the hybrid choice was wrong (headers are supported); hybrid still stands on key revocability, but the frame should not cite that premise; TLS on C3 is proven upstream
  - seeds: `c64`
- `s24` — `challenge pass / security lens: crosspoint src/WifiCredentialStore.h + .cpp:17`: credentials persist on SD obfuscated, not in NVS; contradicts c59 as worded
  - seeds: `c65`
- `s25` — `challenge pass / recovery lens: pocketink flash guide (bootloop risk) + crosspoint-tools repair`: no rollback path existed in the frame for a failed first flash of the only unit on hand
  - seeds: `c66`
- `s26` — `challenge pass / adjacent-systems lens: cultureflare/_remote_login/*.py (grep path|bypass: no hits)`: remote-login has no path-scoped Access or bypass rules; the hybrid decision c37 has a hidden cross-repo dependency
  - seeds: `c67`
- `s27` — `challenge pass / security lens: hybrid auth (c37) vs direct LAN origin access`: Access only protects the tunnel path; LAN clients hit the origin directly, so the origin must decide its own LAN auth policy
  - seeds: `c68` (rejected)
- `s28` — `challenge pass / adjacent-systems lens: ss -ltn + systemctl is-active avahi-daemon + docker ps on spark`: port plan must avoid 8000/8001/8770/8791; mDNS advertisement belongs to host avahi; existing containers (model-gear, culture-rules-mongod, weather) share the host
  - seeds: `c69`
- `s29` — `challenge pass / UX lens: crosspoint src/ReaderFontSizes.h`: zoom maps to discrete point sizes; reflow on the C3 is slow and renumbers pages, which the go-to-page menu (c8) must account for
  - seeds: `c70`
- `s30` — `challenge pass / input lens: crosspoint src/MappedInputManager.h`: logical buttons are Back, Confirm, Left, Right, Up, Down, Power, PageBack, PageForward; the user's 'top' key most likely maps to Up/Down (needs on-device check, v2); remapping via ButtonRemapActivity exists
  - seeds: `c7`
- `s31` — `challenge pass / data-flow lens: crosspoint README formats + culture-rules output (JSON/markdown, no epub)`: agent-generated docs will not be in a device format; conversion is an unplanned dependency of the MCP push story
  - seeds: `c71` (rejected)
- `s32` — `challenge pass / lifecycle lens: c55 sync contract`: contract covered add/ACK only; delete propagation, SD-full and key revocation were unstated
  - seeds: `c72`
- `s33` — `challenge pass / observability lens: frame-wide`: no signal existed for 'did the book reach the device' beyond the user checking the reader
  - seeds: `c73`
- `s34` — `challenge pass / containment lens: reterminal-cli board/pdf.py pattern + public upload endpoint`: uploads become reachable over the tunnel with only a key; no input containment was specified
  - seeds: `c74`
- `s35` — `challenge pass / depth + entry condition`: rigorous (hardware, security, distributed state, data loss); run before /think converged because confirmations were pending, so findings join the same review; lenses swept: adjacent systems, counter-evidence, lifecycle, security, recovery, UX, input, data flow, observability, containment

## Decisions

- Server/API/MCP runtime deps (HTTP framework, MCP SDK) ship as an optional extra (e.g. xteink\[server\]) so the base CLI keeps dependencies = \[\] (pyproject.toml:16); the docker image installs the extra
- Firmware = a fork of CrossPoint Reader (now crosspoint-reader/crosspoint-reader, default branch develop; MIT, PlatformIO) with our own theme/UI, button map and server-sync, not a from-scratch firmware: it already supports X3/X4 (ESP32-C3) and X4Pro/X4C (ESP32-S3) from one codebase, saved-network STA auto-join (max 8), OPDS, EPUB/TXT/BMP/XTC
- Firmware is a CrossPoint Reader fork in its own agentculture repo (not firmware/ in xteink); xteink owns server/API/MCP/CLI/web/compose and the device sync protocol contract
- Auth is hybrid: Cloudflare Access (email SSO) gates the web UI at ebooks.culture.dev; device, API and MCP paths use an xteink-enforced API key so firmware never sends CF-Access headers
- 'iPhone (5)' is the hotspot SSID; firmware stores it as a saved network alongside the home LAN SSID
- Zoom UX: the top button toggles zoom mode (shows/hides an on-screen zoom scale); while zoom mode is on, left/right decrease/increase zoom (right = larger text); while it is off, left/right turn pages
- MCP server uses the official mcp Python SDK (not FastMCP), matching culture-rules and agentfront
- Leftover template strings are fixed in this repo before /think (separate small PR)
- Provisioning is over USB: 'xteink device provision --port /dev/ttyACM0 --apply' writes saved networks (home LAN + 'iPhone (5)'), server URLs and a freshly minted per-device key over serial; the device key is stored in NVS, Wi-Fi creds in upstream's obfuscated SD store
- Device tries the LAN server first (mDNS xteink.local via host avahi, or provisioned IP), then falls back to <https://xteink.culture.dev> with its device key, so it can download over the iPhone hotspot
- Device key lives in ESP32 NVS (internal flash) and is revocable; Wi-Fi credentials stay in upstream's hardware-key-obfuscated /.crosspoint/wifi.json on the microSD
- Two hostnames via cultureflare: ebooks.culture.dev = web UI behind Cloudflare Access SSO; xteink.culture.dev = tunnel-only (--no-access) endpoint for the device, authenticated by the xteink device key
- LAN auth: API, MCP and device endpoints always require a key (LAN included); the web UI is open on the LAN and gated by Access only on the tunnel
- Conversion in issue 1: Markdown/HTML -> EPUB server-side (pandoc in the image); PDF conversion is a follow-up
- Remote MCP/API is out of scope for issue 1: only clients inside our network (home LAN, Tailscale, Culture mesh hosts) can push books and articles; xteink.culture.dev serves device endpoints only

## Hard questions

- Upstream keeps Wi-Fi passwords on the microSD (obfuscated with a hardware key, /.crosspoint/wifi.json); c59 says secrets never go on the SD. Accept upstream's obfuscated-on-SD storage (cheap, keeps c53's minimal diff) or move Wi-Fi creds + device key to ESP32 NVS (diverges from upstream)? (resolved: Device key in NVS (revocable); Wi-Fi creds stay obfuscated on SD per upstream)
- Path-scoped Access via a cultureflare enhancement, or two hostnames (UI behind Access, API/device tunnel-only with app key)? (resolved: Two hostnames: ebooks.culture.dev (Access SSO, web UI) and xteink.culture.dev (tunnel-only, device key))

## Open parks

- [unknown_nonblocking] X3 USB lock status and stock firmware version (esptool get-security-info pending; device must be awake on ttyACM0). Locked => flash via SD update.bin / OTA Unlocker and USB provisioning (c59) may be unavailable
- [unknown_nonblocking] Exact physical X3 button set: which key is 'top' and whether a second top key exists (c43); verify on the unit before finalizing the input map in the fork
- [unknown_nonblocking] TLS memory headroom on ESP32-C3 alongside the EPUB renderer is unmeasured
- [unknown_nonblocking] Real-world sync time and battery cost per sync on the X3 (Wi-Fi join + TLS + download) is unmeasured; the 60 s success signal (c48) may need revising after the first hardware run
- [unknown_nonblocking] Upstream CrossPoint moves fast (pushed 2026-10-06); merge cadence and conflict cost for the fork are unknown until the first upstream sync
- [unknown_nonblocking] Unexamined in this pass: X4Pro/X4C (ESP32-S3) hardware behaviour, iOS hotspot edge cases (sleep, SSID with spaces/parentheses), Cloudflare tunnel limits on large EPUB uploads (100 MB request cap on free plans, unverified)
