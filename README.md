# xteink

Control Xteink e-ink readers privately. xteink is a local server with a
file/book service, a web UI, an HTTP API and an MCP server, plus optional remote
access through Cloudflare Tunnel and custom device firmware that joins Wi-Fi to
sync books locally so reading works fully offline. Your library never leaves
hardware you own: there is no cloud service, no account and no telemetry.

## Status

What exists and runs today:

- A local server (`xteink.server`) with a library, device registry, API keys and
  a device sync protocol (v1, [`docs/device-protocol.md`](docs/device-protocol.md)).
- A web UI served by the same server (upload, library, send to device).
- An MCP server (`xteink.mcp`) so agents can push files and queue them for a
  device. See [`docs/mcp.md`](docs/mcp.md).
- A Docker image and `compose.yaml`, with an opt-in `remote` profile for two
  Cloudflare Tunnels. See [`docs/remote-access.md`](docs/remote-access.md).
- The agent-first CLI (`xteink server|library|device|tunnel|mcp ...`) and the
  AgentCulture mesh identity, harness prompts, skill kit and CI/CD baseline.

What is **not** verified yet:

- **The device side.** The firmware lives in a separate repo,
  [`agentculture/xteink-firmware`](https://github.com/agentculture/xteink-firmware)
  (a CrossPoint Reader fork: theme, zoom mode, USB provisioning, pinned-root
  TLS, OTA from fork releases). Its sync client is still being built, and
  nothing has been verified on real hardware. Treat "a reader syncs books from
  this server" as **firmware fork in progress; hardware verification pending**.
  The server side of the protocol is implemented and tested without a device.

## Architecture

```text
 browser / curl / agents                      Xteink reader (firmware fork, pending)
        |                                              |
        | Bearer xtk_... (API key)                     | Bearer xtd_... (device key)
        v                                              v
 +--------------------------------------------------------------+
 | api container                                                |
 |   main app    :8780  web UI + /api/library, /api/devices,    |
 |                      /api/keys  (API key required)           |
 |   device app  :8781  /api/device/* only (device key)         |
 |   SQLite + files in /data (volume xteink-data)               |
 +--------------------------------------------------------------+
        ^
        | XTEINK_URL + XTEINK_API_KEY
 +--------------+
 | mcp :8782    |  streamable-http for LAN / tailnet / mesh agents
 +--------------+

 Optional (compose --profile remote, see docs/remote-access.md):
   cloudflared-ui      ebooks.culture.dev -> api:8780  (Cloudflare Access SSO)
   cloudflared-device  xteink.culture.dev -> api:8781  (device app only)
```

The main app and the device app are separate processes on separate ports on
purpose. A tunnel points at port 8781 only, so remote exposure is limited by
port: the device app does not mount any library, admin or docs route.

## Quickstart

You need Docker with the compose plugin and `git`. Nothing else: the image
builds the web UI and bundles pandoc (Markdown/HTML to EPUB).

```bash
git clone https://github.com/agentculture/xteink.git
cd xteink

# 1. Start the server (builds the image on first run; takes a few minutes).
docker compose up -d api

# 2. Mint the first API key. It is printed once and only its hash is stored.
docker compose run --rm api python -m xteink.server create-key admin
# -> xtk_...   (copy it now)

# 3. Open the web UI and connect this browser with that key.
#    http://<host>:8780   (use http://localhost:8780 on the same machine)

# 4. Upload a book or article in the UI, or via the API:
curl -H "Authorization: Bearer <api-key>" \
     -F "file=@my-article.md" -F "title=My article" \
     http://localhost:8780/api/library
curl -H "Authorization: Bearer <api-key>" http://localhost:8780/api/library
```

Uploads accept EPUB, BMP and TXT as-is, and Markdown/HTML converted to EPUB.
PDF is not supported yet. See [`docs/api.md`](docs/api.md) for every endpoint and
error code.

### Ports and settings

Copy `.env.example` to `.env` to change anything. The useful variables:

| Variable | Default | Meaning |
|----------|---------|---------|
| `XTEINK_PUBLISH_PORT` | `8780` | Host port for the web UI and main API |
| `XTEINK_PUBLISH_DEVICE_PORT` | `8781` | Host port for the device app |
| `XTEINK_PUBLISH_MCP_PORT` | `8782` | Host port for the MCP server |
| `XTEINK_PUBLISH_BIND` | `0.0.0.0` | Interface to publish on; `127.0.0.1` keeps it host-local |
| `XTEINK_DATA_DIR` | named volume | Host directory for the library (writable by uid 10001) |
| `COMPOSE_PROJECT_NAME` | `xteink` | Prefix for containers and the volume |

Every port is protected by keys, including on the LAN. Binding to `0.0.0.0`
exposes the web UI shell (not your data) to your network; set
`XTEINK_PUBLISH_BIND=127.0.0.1` if that is not what you want.

### MCP for agents (optional)

Mint a second key for the MCP service, put it in `.env`, and start everything:

```bash
docker compose run --rm api python -m xteink.server create-key mcp
cp .env.example .env     # then set XTEINK_API_KEY=<the printed key>
docker compose up -d
```

The MCP endpoint is then `http://<host>:8782/mcp`. Without a key the `mcp`
service refuses to start, which is why step 1 above starts only `api`. See
[`docs/mcp.md`](docs/mcp.md). MCP is for LAN, Tailscale and mesh use; it is
never routed through the tunnel.

### Remote access (optional)

`docker compose --profile remote up -d` adds two cloudflared connectors, one for
the web UI behind Cloudflare Access and one for device-only sync. Tunnels, DNS
and Access policy are provisioned separately with cultureflare. The full steps,
including the hidden-secret handling for the tunnel tokens, are in
[`docs/remote-access.md`](docs/remote-access.md).

### Provisioning a device (pending hardware verification)

The commands exist and are dry-run by default; the end-to-end flow has not been
run on real hardware yet.

```bash
# 1. Back up the stock flash over USB first (reads only; dry-run without --apply).
uv run xteink device backup --port /dev/ttyACM0 --apply

# 2. Flash the firmware fork from agentculture/xteink-firmware (see that repo).

# 3. Mint a device key and send Wi-Fi, server URLs and the key over USB.
export XTEINK_URL=http://localhost:8780 XTEINK_API_KEY=<api-key>
uv run xteink device provision --port /dev/ttyACM0 --name my-reader \
    --lan-url http://<host>:8781 --apply
```

`xteink` here is the CLI from this repo (see Development below). Wi-Fi
passwords are read from `~/.config/xteink/networks.json` (keep it `chmod 600`,
never commit it) or prompted, never passed as flags. The device speaks to the
device app on port 8781 with its own `xtd_` key; it can only download what you
queued for it. Queue an item with `xteink device queue` or the web UI. See
[`docs/device-protocol.md`](docs/device-protocol.md).

### Local name

Containers do not do mDNS, so `xteink.local` is not provided by compose. See
[`docker/avahi/`](docker/avahi/) for running an Avahi publisher on the host, or
use the host's IP or a DNS name.

## Development

```bash
uv sync --extra server              # runtime + server + dev deps
uv run pytest -n auto               # test suite
uv run python -m xteink.server serve   # run both apps locally (data in the default data dir)
cd web && npm ci && npm run build   # build the web UI into xteink/server/_webassets
```

[`CLAUDE.md`](CLAUDE.md) has the full command list, lint gates and conventions.

## What you get

- **An agent-first CLI** cited from [teken](https://github.com/agentculture/teken)
  (`afi-cli`) — the runtime package has no third-party dependencies.
- **A mesh identity** — `culture.yaml` (`suffix` + `backend`) and the matching
  resident prompt file (`CLAUDE.md`, since this agent runs
  `backend: claude`). The mesh resident is one of **two separate
  selections** over this clone — see
  [Two selections, not one](#two-selections-not-one) below.
- **Four harness prompt files**, one per agent harness, each read by exactly
  one of them (see [Prompt files by harness](#prompt-files-by-harness) below).
  All four harnesses are usable interactively regardless of which one
  `culture.yaml` names as the mesh resident.
- **The canonical guildmaster skill kit** (19 skills) under `.claude/skills/`,
  vendored cite-don't-import. See [`docs/skill-sources.md`](docs/skill-sources.md).
- **A build + deploy baseline** — pytest, lint, the agent-first rubric gate, and
  PyPI Trusted Publishing wired into GitHub Actions.

## Prompt files by harness

Four harnesses, four root files, no shared base — each file is read by
exactly one harness:

| Harness | File(s) |
|---------|---------|
| Claude Code | [`CLAUDE.md`](CLAUDE.md) |
| Pi / associate | [`AGENTS.override.md`](AGENTS.override.md) + [`.pi/SYSTEM.md`](.pi/SYSTEM.md) |
| colleague | [`AGENTS.colleague.md`](AGENTS.colleague.md) |
| Qwen Code | [`QWEN.md`](QWEN.md) |

**Claude Code** — `CLAUDE.md` is the fullest write-up of the repo's
conventions; read it first.

**Pi / associate** — `AGENTS.override.md` replaces this directory's
`AGENTS.md`/`CLAUDE.md` in Pi's context layer, so Pi does not inherit
`CLAUDE.md`. `.pi/SYSTEM.md` replaces Pi's default system prompt with the
non-coding `associate` identity (read/find/summarize only).

**colleague** — colleague's prompt cascade is `AGENTS.md` →
`AGENTS.colleague.md` → `AGENTS.colleague.<model>.md`. This repo ships only
the middle layer: there is no `AGENTS.md` (a shared base across harnesses was
considered and rejected) and no per-model override file.

**Qwen Code** — Qwen Code reads `QWEN.md` and `AGENTS.md`; since there is no
`AGENTS.md`, `QWEN.md` is its sole source of guidance.

There is intentionally **no `AGENTS.md`** at the root — each harness gets an
unrelated file rather than cascading from a shared base.

## Two selections, not one

It is tempting to read "switch harness" as one decision. It is actually two,
and this repo keeps them separate:

1. **The interactive harness** — which binary you run (`claude`, `pi`,
   `colleague`, `qwen`). `cd` into the clone and run any of them; all four
   are live simultaneously, and none of them requires editing a file or
   flipping a switch. A harness can be force-selected for one invocation
   (e.g. a CI smoke check) without ever touching `culture.yaml` — see
   [`docs/automation-contract.md`](docs/automation-contract.md).
2. **The mesh resident** — the single `backend` `culture.yaml` declares,
   which is what the Culture daemon starts and what `steward doctor`
   checks. `guild harness use <name>` changes only this.

`culture.yaml`'s `backend` affects (2) only. It never affects which harness
you can invoke interactively in (1). See
[`docs/harness-selection.md`](docs/harness-selection.md) for the full
writeup, including who reads this config and why existing siblings are not
retrofitted by this arc.

## Agent scaffold quickstart

```bash
uv sync
uv run pytest -n auto                 # run the test suite
uv run xteink whoami  # identity from culture.yaml
uv run xteink learn   # self-teaching prompt (add --json)
uv run teken cli doctor . --strict    # the agent-first rubric gate CI runs
```

## CLI

| Verb | What it does |
|------|--------------|
| `whoami` | Report this agent's nick, version, backend, and model from `culture.yaml`. |
| `learn` | Print a structured self-teaching prompt. |
| `explain <path>` | Markdown docs for any noun/verb path. |
| `overview` | Read-only descriptive snapshot of the agent. |
| `doctor` | Check the agent-identity invariants (prompt-file-present, backend-consistency). |
| `cli overview` | Describe the CLI surface itself. |
| `server status` | Probe the API, the key and the device app. |
| `library list \| add \| rm` | List/search, upload, remove items. `add` and `rm` are dry-run unless `--apply`. |
| `device list \| queue \| revoke \| backup \| provision` | Manage readers. Mutating verbs are dry-run unless `--apply`. |
| `tunnel status \| plan` | Probe the public hostnames; print the cultureflare commands (never executed). |
| `mcp serve` | Run the MCP server (stdio, or `--http`). |

The `server`, `library`, `device` and `mcp` nouns talk to the API using
`XTEINK_URL` (default `http://127.0.0.1:8780`) and `XTEINK_API_KEY`.

Every command supports `--json`. Results go to stdout, errors/diagnostics to
stderr (never mixed). Exit codes: `0` success, `1` user error, `2` environment
error, `3+` reserved.

## Contributing

See [`CLAUDE.md`](CLAUDE.md) for the conventions:

- Every PR bumps the version.
- PRs go through the `cicd` lane.
- Worktrees live in a repo-named folder.
- Deploys use PyPI Trusted Publishing.

If you change project facts, update all four harness prompt files together.

## License

Apache 2.0 — see [`LICENSE`](LICENSE).
