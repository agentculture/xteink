"""Markdown catalog for ``xteink explain <path>``.

Each entry is verbatim markdown. Keys are command-path tuples. The empty tuple
and ``("xteink",)`` both resolve to the root entry.

Keep bodies self-contained: an agent reading one entry should get enough
context without chaining reads.
"""

from __future__ import annotations

_ROOT = """\
# xteink

Private, local-first control for Xteink e-ink readers: a local book server,
optional remote access through a Cloudflare Tunnel, and custom reader firmware
that syncs books over Wi-Fi so reading works fully offline. Your library never
leaves hardware you own.

xteink is also an AgentCulture mesh agent. It ships the library server (HTTP
API on port 8780, a device-only sync app on 8781, and the web UI), an MCP server
(`push_file`, `list_library`, `send_to_device`), and this agent-first CLI (cited
from the teken `python-cli` reference), plus a docker compose stack. The reader
firmware is a separate fork (agentculture/xteink-firmware) and is pending
hardware verification. See `xteink learn` for the command map.

## Verbs

- `xteink whoami` — identity probe from `culture.yaml`.
- `xteink learn` — structured self-teaching prompt.
- `xteink explain <path>` — markdown docs for any noun/verb.
- `xteink overview` — descriptive snapshot of the agent.
- `xteink doctor` — check the agent-identity invariants.
- `xteink cli overview` — describe the CLI surface.

## Exit-code policy

- `0` success
- `1` user-input error
- `2` environment / setup error
- `3+` reserved

## See also

- `xteink explain whoami`
- `xteink explain doctor`
"""

_WHOAMI = """\
# xteink whoami

Reports the agent's identity from `culture.yaml`: nick (`suffix`), backend,
served model, and the package version. Read-only.

## Usage

    xteink whoami
    xteink whoami --json
"""

_LEARN = """\
# xteink learn

Prints a structured self-teaching prompt covering purpose, command map,
exit-code policy, `--json` support, and the `explain` pointer.

## Usage

    xteink learn
    xteink learn --json
"""

_EXPLAIN = """\
# xteink explain <path>

Prints markdown documentation for any noun/verb path. Unlike `--help` (terse,
positional), `explain` is global and addressable by path.

## Usage

    xteink explain xteink
    xteink explain whoami
    xteink explain --json <path>
"""

_OVERVIEW = """\
# xteink overview

Read-only descriptive snapshot of the agent: identity (from `culture.yaml`), the
verb surface, and the sibling-pattern artifacts the repo carries. Accepts an
ignored `target` so a stray path never hard-fails.

## Usage

    xteink overview
    xteink overview --json
"""

_DOCTOR = """\
# xteink doctor

Checks the agent-identity invariants `steward doctor` verifies:
prompt-file-present and backend-consistency (`claude` → `CLAUDE.md`), plus a
skills-present check. Exits 1 when unhealthy.

prompt-file-present requires the *resident* prompt the declared backend
actually reads. Other harness prompt files recognized under the same backend
name (`AGENTS.override.md`, `.pi/SYSTEM.md`, `QWEN.md`) belong to
interactively available harnesses the mesh daemon never loads; they are
reported by the informational harness-prompts check and never substituted.

## Usage

    xteink doctor
    xteink doctor --json
"""

_CLI = """\
# xteink cli

Noun group for CLI-surface introspection. `cli overview` describes the CLI
itself (distinct from the global `overview`, which describes the agent).

## Usage

    xteink cli overview
    xteink cli overview --json
"""


_SERVER = """\
# xteink server

Health of the xteink HTTP API, as seen from the CLI. `status` probes `GET /` on
`XTEINK_URL` (default `http://127.0.0.1:8780`), checks that `XTEINK_API_KEY` works
with a cheap authenticated call, and probes the device app
(`XTEINK_DEVICE_URL`, default `http://127.0.0.1:8781`; a 401 on
`/api/device/whoami` means alive). The key is never printed.

## Usage

    xteink server status [--json]
    xteink server overview

Exit codes: `0` healthy, `1` key rejected, `2` server unreachable.
"""

_LIBRARY = """\
# xteink library

Manage the library through the HTTP API (no direct database access).
`add` and `rm` are **dry-run unless `--apply`**: they say what they would do and
send no write request.

## Usage

    xteink library list [--q TEXT] [--kind book|article|image] [--limit N] [--json]
    xteink library add PATH [--title T] [--author A] [--kind K] [--device ID|NAME] [--apply]
    xteink library rm ID [--apply]
    xteink library overview

`add --device` also queues the new item for that device (after upload, with
`--apply`). Needs `XTEINK_API_KEY`; exit `2` when the server is unreachable or no
key is set, `1` for API errors such as an unknown id.
"""

_DEVICE = """\
# xteink device

List devices and manage their queues/keys through the HTTP API. DEVICE is an id
or a name. `queue` and `revoke` are **dry-run unless `--apply`**.

## Usage

    xteink device list [--json]
    xteink device queue DEVICE ITEM_ID [--apply]
    xteink device revoke DEVICE [--apply]
    xteink device backup --port PORT [--esptool CMD] [--chip C] [--apply] [--json]
    xteink device provision --port PORT [--name N] [--networks-file P | --no-networks]
                            [--lan-url U] [--tunnel-url U] [--replace-networks] [--apply] [--json]
    xteink device overview

## USB verbs (`backup`, `provision`)

Both are **dry-run unless `--apply`** and never touch hardware without it.

- `backup` runs `esptool` (external tool, default `uvx esptool@latest`, override with
  `--esptool`): `read-mac`, `flash-id`, then `read-flash 0x0 <size> <out>`. The dump and a
  `.sha256` file land in `<data dir>/backups/<MAC>/<UTC timestamp>-full.bin`
  (`XTEINK_DATA_DIR`, else `~/.local/share/xteink`). Dry-run prints the exact commands.
- `provision` first needs Settings > System > Provision via USB open on the device. With
  `--apply` it sends a hello, mints a device key via the API, sends networks, server URLs and
  the key over the serial port (`XTEINK-PROV 1` protocol), checks the ACK's key id and prints
  only the key id. If the device refuses, the minted key is revoked again.
- Wi-Fi networks come from `--networks-file` (default `~/.config/xteink/networks.json`: a JSON
  list of `{ssid, password}`, must be `chmod 600`, never commit it) or an interactive prompt.
  Passwords are never accepted as flags, and the device key and passwords are never printed.
"""

_TUNNEL = """\
# xteink tunnel

Remote access through a Cloudflare Tunnel. xteink never calls the Cloudflare API.

- `status` probes the two public hostnames over HTTPS: the device host's
  `/api/device/whoami` should answer 401 (reachable, key-gated) and the UI host
  should answer with a Cloudflare Access redirect/login (3xx/401/403). Each is
  reported reachable / unreachable / unexpected; network failures never fail
  hard unless `--strict` (then exit 2).
- `plan` prints (never runs) the two `cultureflare remote-login setup` commands.
  cultureflare is dry-run until you add `--apply` yourself.

## Usage

    xteink tunnel status [--ui-host H] [--device-host H] [--strict] [--json]
    xteink tunnel plan [--allow EMAIL] [--ui-host H] [--device-host H]
                       [--ui-port N] [--device-port N]
    xteink tunnel overview

Env: `XTEINK_UI_HOST` (default `ebooks.culture.dev`), `XTEINK_DEVICE_HOST`
(default `xteink.culture.dev`), `XTEINK_OWNER_EMAIL`.
"""

_MCP = """\
# xteink mcp

Serve the xteink MCP tools (a thin client of the HTTP API). Delegates to
`python -m xteink.mcp`; requires the server extra (`pip install 'xteink[server]'`)
and `XTEINK_API_KEY`.

## Usage

    xteink mcp serve [--http] [--bind ADDR] [--port N]
    xteink mcp overview

stdio is the default transport; `--http` selects streamable-http.
"""


ENTRIES: dict[tuple[str, ...], str] = {
    (): _ROOT,
    ("xteink",): _ROOT,
    ("whoami",): _WHOAMI,
    ("learn",): _LEARN,
    ("explain",): _EXPLAIN,
    ("overview",): _OVERVIEW,
    ("doctor",): _DOCTOR,
    ("cli",): _CLI,
    ("cli", "overview"): _CLI,
    ("server",): _SERVER,
    ("server", "overview"): _SERVER,
    ("server", "status"): _SERVER,
    ("library",): _LIBRARY,
    ("library", "overview"): _LIBRARY,
    ("library", "list"): _LIBRARY,
    ("library", "add"): _LIBRARY,
    ("library", "rm"): _LIBRARY,
    ("device",): _DEVICE,
    ("device", "overview"): _DEVICE,
    ("device", "list"): _DEVICE,
    ("device", "queue"): _DEVICE,
    ("device", "revoke"): _DEVICE,
    ("device", "backup"): _DEVICE,
    ("device", "provision"): _DEVICE,
    ("tunnel",): _TUNNEL,
    ("tunnel", "overview"): _TUNNEL,
    ("tunnel", "status"): _TUNNEL,
    ("tunnel", "plan"): _TUNNEL,
    ("mcp",): _MCP,
    ("mcp", "overview"): _MCP,
    ("mcp", "serve"): _MCP,
}
