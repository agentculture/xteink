# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

`xteink` lets you control Xteink e-ink readers privately: a local server with a
file/book service, optional remote access via Cloudflare Tunnel, and custom
device firmware that joins Wi-Fi to sync books locally, so reading works fully
offline. Your library never leaves hardware you own.

It is also an AgentCulture mesh agent (suffix `xteink`), scaffolded from
`culture-agent-template`. It follows the sibling pattern every Culture agent
uses: an agent-first CLI, a mesh identity, the canonical skill kit, and a
buildable/deployable package baseline. Related projects:
[`guildmaster`](https://github.com/agentculture/guildmaster) supplies the skills,
[`steward`](https://github.com/agentculture/steward) handles alignment
(`steward doctor`), and [`teken`](https://github.com/agentculture/teken) is the
afi-cli scaffolder the CLI is cited from.

### Current state vs. roadmap

Landed and in the tree (read the code, not this list, when in doubt):

- **Core** (`xteink/core`): SQLite store plus content-addressed blobs, library,
  devices and queue, API/device keys, and ingest (size and zip-bomb limits,
  Markdown/HTML to EPUB through pandoc).
- **Server** (`xteink/server`): the main app on :8780 (`/api/library*`,
  `/api/devices*`, `/api/keys*`, the web UI at `/`, OpenAPI at `api/openapi.json`)
  and a separate device-only app on :8781 (`/api/device/*`, device protocol v1 in
  `docs/device-protocol.md`). Run with `python -m xteink.server serve|create-key`.
  Both apps require keys, including on the LAN; the main app also accepts a
  verified Cloudflare Access JWT when `XTEINK_ACCESS_TEAM_DOMAIN` and
  `XTEINK_ACCESS_AUD` are set (`xteink/server/access.py`, cited from culture-rules).
- **MCP** (`xteink/mcp`, official `mcp` SDK): tools `push_file`, `list_library`,
  `send_to_device`; stdio by default, `--http` on :8782. LAN/tailnet/mesh only,
  never tunnelled. `xteink/client.py` is the stdlib API client behind the CLI and MCP.
- **Web UI** (`web/`, Vite + React): built into `xteink/server/_webassets`
  (git-ignored, built by the Dockerfile). Behind Cloudflare Access it needs no
  key; on the LAN the first run asks for an API key.
- **Packaging**: `Dockerfile` and `compose.yaml` (`api`, `mcp`; the `remote`
  profile adds `cloudflared-ui` and `cloudflared-device`), `docker/avahi/` notes
  for `xteink.local`, pandoc 3.12 in the image.
- **Remote access**: two cultureflare tunnels (see `docs/remote-access.md`):
  `ebooks.culture.dev` behind Cloudflare Access to `api:8780`, and
  `xteink.culture.dev` tunnel-only to `api:8781`. Tokens are hidden grant secrets
  injected with `grant run --inject`; xteink never calls the Cloudflare API.
- **CLI nouns**: `server`, `library`, `device` (`list`, `queue`, `revoke`,
  `backup`, `provision`), `tunnel` (`status`, `plan`), `mcp` (`serve`), beside
  `whoami`, `learn`, `explain`, `overview`, `doctor`, `cli overview`. Mutating
  verbs are dry-run unless `--apply`.
- User docs: `README.md` (quickstart), `docs/api.md`, `docs/mcp.md`.

Still **(planned)** or unverified:

- **(in progress, unverified)** Custom device firmware. It lives in a separate
  repo, `agentculture/xteink-firmware` (a CrossPoint Reader fork: theme, zoom mode,
  USB provisioning, pinned-root TLS, OTA from fork releases). Its sync client is
  still being built and nothing has been verified on hardware. Do not claim that a
  device syncs end to end. The server side of the protocol is implemented and tested
  against a fake device.
- **(planned)** PDF ingest (rejected today with `pdf_not_supported`).

Some CLI strings (`xteink/cli/_commands/learn.py`, `xteink/explain/catalog.py`)
may still describe the server, API, MCP and web UI as planned. They have landed;
keep those strings honest.

When you add a product component, put it under a new CLI noun group (see
[The CLI](#the-cli)) instead of a separate entry point. When a planned item
lands, update this section and the other three prompt files.

## Commands

```bash
uv sync                                        # install runtime + dev deps
uv run pytest -n auto                          # full suite (xdist)
uv run pytest tests/test_cli.py -v             # one file
uv run pytest tests/test_cli.py::test_name -v  # one test
uv run pytest -n auto --cov=xteink --cov-report=term   # coverage (fail_under = 60)

uv run black --check xteink tests              # lint, as CI runs it
uv run isort --check-only xteink tests
uv run flake8 xteink tests
uv run bandit -c pyproject.toml -r xteink
markdownlint-cli2 "**/*.md" "#node_modules" "#.local" "#.claude/skills" "#.teken"
uv run teken cli doctor . --strict             # agent-first rubric gate
python3 scripts/scan-secrets.py                # secrets / non-localhost endpoint gate
uv run python scripts/harness-smoke.py --stage config   # per-harness config check

uv sync --extra server                         # also install fastapi/uvicorn/mcp (server + MCP tests)
python -m xteink.server serve                  # main app :8780 + device app :8781
python -m xteink.server create-key <name>      # mint an API key (printed once)
python -m xteink.mcp [--http]                  # MCP server: stdio, or :8782
uv run python scripts/export-openapi.py --check   # api/openapi.json must match the app

cd web && npm ci && npm run build              # web UI -> xteink/server/_webassets
cd web && npm test && npm run typecheck        # vitest + tsc

docker compose up -d api                       # the stack (set COMPOSE_PROJECT_NAME for a scratch one)
scripts/check-compose.sh                       # validate compose.yaml (no containers started)

uv run xteink whoami      # identity from culture.yaml (every verb takes --json)
uv run xteink doctor      # agent-identity invariants
```

All of the above runs in CI (`.github/workflows/tests.yml`). The jobs are
`test` (with SonarCloud when `SONAR_TOKEN` is set), `lint`, `harness-smoke`,
and `version-check`.

`scripts/scan-secrets.py` fails on any `http(s)://` value under a
`url`/`host`/`endpoint`/`baseUrl`-shaped key in a tracked JSON file unless the
host is localhost. Keep real server addresses, tunnel hostnames, and Wi-Fi or
Cloudflare credentials out of tracked config. Use example files or env vars
instead (`.claude/skills.local.yaml.example` and `.qwen/settings.json.example`
show the pattern).

## The CLI

The CLI is cited (cite-don't-import) from teken's `python-cli` reference, so the
runtime package has **no third-party dependencies** (`dependencies = []`).
`teken` is a dev dependency only. If you add a runtime dependency, do it on
purpose.

How it fits together:

- `xteink/cli/__init__.py` builds the argparse tree. Each verb or noun module
  under `xteink/cli/_commands/` exposes `register(sub)`. New noun groups are
  registered in `_build_parser()`, where a comment marks the spot.
- Handlers either return `None`/`int` or raise `CliError`
  (`xteink/cli/_errors.py`). `_dispatch` turns any other exception into a
  `CliError`, so no traceback reaches the user. Argparse errors go through the
  same path via `_CliArgumentParser.error`.
- Output goes through `xteink/cli/_output.py`. Results go to stdout and
  errors/diagnostics to stderr, never mixed. JSON mode is chosen by scanning raw
  argv for `--json` before parsing, so parse errors can also render as JSON.
- Exit codes: `0` success, `1` user error, `2` environment error, `3+` reserved.
- `explain <path>` reads markdown from `xteink/explain/catalog.py`, keyed by
  command-path tuples. When you add a verb or noun, add a catalog entry too, then
  re-run `uv run teken cli doctor . --strict`.
- The `server`, `library`, `device` and `mcp` nouns call the HTTP API through
  `xteink/client.py` (`XTEINK_URL`, default `http://127.0.0.1:8780`, and
  `XTEINK_API_KEY`). Mutating verbs take `--apply`; without it they only print
  what they would do. `device backup|provision` drive esptool/USB serial.
- `whoami` and `doctor` read `culture.yaml`, located by
  `find_culture_yaml` in `_commands/whoami.py`.

## Identity and the four harnesses

`culture.yaml` declares `suffix: xteink` and `backend: claude`. That makes this
file the **mesh-resident prompt**: the file the Culture daemon loads for this
agent. `xteink doctor` and `steward doctor` check
**prompt-file-present** and **backend-consistency** (`claude` ↔ `CLAUDE.md`).

The repo root has one prompt file per interactive harness. Each file is read by
exactly one harness, and on purpose there is **no shared `AGENTS.md`**.
`harness-smoke.py` fails CI if one appears, because it would shadow the Pi and
colleague files.

| Harness | File(s) |
|---------|---------|
| Claude Code | `CLAUDE.md` |
| Pi / associate (read-only, non-coding) | `AGENTS.override.md` (context) + `.pi/SYSTEM.md` (system prompt) |
| colleague | `AGENTS.colleague.md` |
| Qwen Code | `QWEN.md` |

There are two separate selections here:

1. **The interactive harness:** whichever binary you run. All four are live
   over the same clone.
2. **The mesh resident:** the single backend in `culture.yaml`.

Forcing a harness for automation is done per invocation only, as described in
`docs/automation-contract.md` and `docs/harness-invocations.yaml`. It never
edits `culture.yaml`. See `docs/harness-selection.md` for details.

**When you change project facts in this file, update the other three prompt
files as well.** The harness-smoke live stage asks each harness whether its file
describes the project as xteink.

`.qwen/skills`, `.pi/skills`, and `.colleague/skills` are relative git symlinks
to `.claude/skills`. They are not copies. Colleague's loader can't read that
layout yet (colleague#494). **Do not run `colleague learn-from claude` here**:
it would write generated files through the symlink into `.claude/skills/`.

## Skills

`.claude/skills/` vendors the canonical guildmaster skill kit
(cite-don't-import). Provenance, local divergences (`devex` rename,
`ask-colleague` from `colleague` directly), and the re-sync procedure are in
`docs/skill-sources.md`. **Do not edit or reformat vendored skill files.** Fixes
go upstream and come back on the next re-sync. Every vendored `SKILL.md` needs
`type: command` in its frontmatter, because the culture skill loader silently
skips skills without it.

Tooling prerequisites:

- `devex` (>=0.21) on PATH: the `cicd` skill uses `devex pr`.
- `agtag` (>=0.1) on PATH: the `communicate` skill uses `agtag issue`.
- `colleague` on PATH (optional): only `ask-colleague` needs it.

## Conventions

- **Every PR bumps the version**, even for docs, config, or CI changes. Use the
  `version-bump` skill, which updates `pyproject.toml` and `CHANGELOG.md`. The
  `version-check` CI job blocks merge otherwise.
- **Open PRs with the `cicd` skill** (`devex pr` plus SonarCloud gating). Its
  scripts sign posts `- xteink (Claude)` automatically, using the nick from
  `culture.yaml`, so don't add a signature to the body yourself.
- **Use `ask-colleague` as a habit.** Before presenting or opening a PR on a
  non-trivial diff, run `review`. Run `explore` when you need a fresh read of an
  unfamiliar area. Both are read-only and run in a throwaway worktree.
  `write --apply` / `write --pr` need the user's go-ahead. Treat colleague's
  output as a second opinion to verify, not as authority.
- **Deploy:** pushes to `main` that touch `pyproject.toml` or `xteink/**`
  publish to PyPI via Trusted Publishing (`.github/workflows/publish.yml`).
  Same-repo PRs publish a `.devN` build to TestPyPI.
- Style: black/isort/flake8 with line length 100, Python 3.12. Markdown lint
  turns off MD013 (line length).

## Worktrees

Git worktrees you create go in `../.worktrees.xteink/<name>/`, one subfolder per
worktree. Never use a shared `../worktrees/`. Use branch prefixes scoped to the
work (`sync/t2`, not `agent/t2`):

```bash
git worktree add ../.worktrees.xteink/<name> -b <scope>/<name>
```

The vendored `assign-to-workforce` skill's example uses `../worktrees/` and
`agent/<id>`. Override both when you follow it. The temporary worktrees that
`ask-colleague` creates under `$TMPDIR` are exempt, because they are deleted
automatically. Clean up with `git worktree remove <path>`. `prune` only clears
metadata for directories that are already gone.

## Memory

Run `/recall` before non-trivial work and `/remember` when a non-obvious
decision, constraint, or gotcha comes up. These are backed by `eidetic`. By
default the wrappers use this agent's private scope (`--scope xteink`, from
`culture.yaml`), which Claude and colleague share. Pass `--visibility public`
to contribute to the shared pool. Don't store what the repo already records.

---

This file describes the repository **as it exists on disk today**. Anything not
built yet is marked `(planned)`.
