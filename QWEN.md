# QWEN.md

This file provides guidance to Qwen Code when working with code in this
repository. Qwen Code's context loader reads exactly `QWEN.md` and `AGENTS.md`
in a directory; this repo deliberately ships only `QWEN.md` — there is no
`AGENTS.md` here (each harness gets its own file; see "Prompt files by
harness" below), so this file is the sole source of project guidance for a
Qwen Code session.

## What this project is

`xteink` lets you control Xteink e-ink readers privately: a local server
with a file/book service, optional remote access via Cloudflare Tunnel, and
custom device firmware that joins Wi-Fi to sync books locally, so reading works
fully offline. Your library never leaves hardware you own. **Landed:** the local
server (main app :8780 with web UI + API, device-only app :8781, both key-gated),
an MCP server (`push_file`, `list_library`, `send_to_device`; stdio or :8782),
Docker/compose packaging, an opt-in two-tunnel Cloudflare setup, and CLI nouns
`server`, `library`, `device`, `tunnel`, `mcp`. The device
firmware (separate repo, `agentculture/xteink-firmware`) is hardware-verified on
the X3: books sync over the home LAN or a phone hotspot and read offline. Other
Xteink models are build-verified only; large (≥ 5 MB) EPUB syncs over HTTPS are
**not verified**. PDF ingest is *(planned)*. User docs: `README.md`, `docs/api.md`,
`docs/mcp.md`. See `CLAUDE.md`, section "Current state vs. roadmap".

It is also an AgentCulture mesh agent (suffix `xteink`), scaffolded from
`culture-agent-template`. It follows the sibling pattern every Culture agent
uses: an agent-first CLI, a mesh identity, the canonical skill kit, and a
buildable/deployable package baseline.

It is a sibling to [`guildmaster`](https://github.com/agentculture/guildmaster)
(the **skills supplier**), [`steward`](https://github.com/agentculture/steward)
(**alignment** — `steward doctor`, the sibling-pattern baseline), and
[`teken`](https://github.com/agentculture/teken) (the **afi-cli** "Agent First
Interface" scaffolder this CLI is cited from) within the Organic Development
framework.

## Prompt files by harness

This repo's root carries one prompt file per agent harness, each read by
exactly one of them — there is no shared base file for them to inherit from:

- **Claude Code** → [`CLAUDE.md`](CLAUDE.md) (the fullest write-up; read it
  first if you are new to the repo).
- **Pi / associate** → [`AGENTS.override.md`](AGENTS.override.md) for context,
  plus [`.pi/SYSTEM.md`](.pi/SYSTEM.md) for its system prompt.
- **colleague** → [`AGENTS.colleague.md`](AGENTS.colleague.md).
- **Qwen Code** → this file.

## Identity

Declared in `culture.yaml`:

```yaml
agents:
- suffix: xteink
  backend: claude
```

`backend: claude` fixes the *mesh resident* prompt file to `CLAUDE.md` — the
mesh runtime reads that file, not this one. A Qwen Code session working in a
clone of this repo is a separate, local tool session; it reads `QWEN.md`
regardless of what `culture.yaml` declares, and running Qwen Code here neither
requires nor changes that declaration. The declaration and the resident prompt
together satisfy the two invariants `steward doctor` verifies:
**prompt-file-present** and **backend-consistency** (`claude` ↔ `CLAUDE.md`).

## The CLI

The CLI is cited (cite-don't-import) from teken's `python-cli` reference
(`teken cli cite`), so the runtime package has **no third-party dependencies**;
`teken` (a.k.a. `afi-cli`) is a dev dependency only. Agent-first verbs:

- `xteink whoami` — identity from `culture.yaml`.
- `xteink learn` — structured self-teaching prompt.
- `xteink explain <path>` — markdown docs for any noun/verb.
- `xteink overview` — descriptive snapshot of the agent.
- `xteink doctor` — check the agent-identity invariants.
- `xteink cli overview` — describe the CLI surface itself.
- `xteink server|library|device|tunnel|mcp ...` — product nouns that call the
  HTTP API (`XTEINK_URL`, `XTEINK_API_KEY`); mutating verbs are dry-run unless
  `--apply`.

Conventions: every command supports `--json`; results go to stdout, errors and
diagnostics to stderr (never mixed); exit codes are `0` success, `1` user
error, `2` environment error, `3+` reserved. The agent-first rubric is
enforced in CI by `teken cli doctor . --strict`.

## Skills

`.claude/skills/` vendors the **canonical guildmaster skill kit**
(cite-don't-import). Provenance and the re-sync procedure live in
`docs/skill-sources.md`. Do not reformat or edit vendored scripts — re-sync
from guildmaster instead.

## Conventions

- **Every PR bumps the version** — even docs/config/CI. Use the
  `version-bump` skill; the `version-check` CI job blocks merge otherwise.
- **Tests**: `uv sync --extra server && uv run pytest -n auto`; web UI: `cd web && npm test`. **Lint**: black, isort, flake8 (line
  length 100), bandit, markdownlint.
- **Deploy**: pushing to `main` publishes to PyPI via Trusted Publishing
  (`.github/workflows/publish.yml`); PRs do a TestPyPI dry-run.

## Layout

```text
xteink/   agent-first CLI (cited from teken's python-cli reference)
  cli/                    parser, error/output contract, _commands/ (verbs)
  explain/                markdown catalog for `explain`
  core/                   store, library, devices, keys, ingest (pandoc)
  server/                 main app :8780 + device app :8781 (FastAPI)
  mcp/                    MCP server (stdio / :8782)
  client.py               stdlib API client
web/                      Vite + React web UI (built into server/_webassets)
Dockerfile, compose.yaml  image and stack (remote profile = cloudflared)
docs/                     api.md, mcp.md, device-protocol.md, remote-access.md
tests/                    pytest smoke + introspection tests
.claude/skills/           vendored guildmaster skill kit (cite-don't-import)
docs/skill-sources.md     skill provenance ledger
culture.yaml              mesh identity (suffix + backend)
.github/workflows/        tests + deploy (PyPI Trusted Publishing)
```

This file describes the repository **as it exists on disk today**. When you
edit, keep claims grounded in checked-in reality; if a section drifts ahead of
reality, mark it `(planned)` or move it under a `## Roadmap` heading. For the
full set of workflow conventions (worktree layout, memory discipline,
`ask-colleague` usage, CLI architecture), see [`CLAUDE.md`](CLAUDE.md) — those conventions apply
to work in this repo regardless of which harness is doing it.
