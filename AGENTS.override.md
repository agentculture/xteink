# AGENTS.override.md

This file is the **context layer** for the Pi harness (the `pi` CLI, and the
`associate` non-coding harness modelled on it) when it runs inside this repo.
Pi's CONTEXT loader concatenates `AGENTS.md` or `CLAUDE.md` from its user-level
config directory (see Pi's own docs), each parent directory, and the working
directory — but an `AGENTS.override.md`
present in a directory replaces that directory's `AGENTS.md`/`CLAUDE.md` entry
outright rather than adding to it. That is why this repo ships this file
instead of an `AGENTS.md`: Pi must **not** inherit `CLAUDE.md` (the Claude Code
guidance file) — the two harnesses read the same repository very differently,
and `CLAUDE.md` assumes a coding session with full repo-write authority that
Pi's non-coding lane does not have.

The identity and behavioral bounds for that lane — who Pi is here, what it may
and may not do — live one layer up, in Pi's **system prompt** file,
[`.pi/SYSTEM.md`](.pi/SYSTEM.md). That file replaces Pi's default
coding-assistant system prompt entirely. This file is project *context* only:
what the repo is and how it is laid out, not who is reading it.

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
`docs/mcp.md`. See `CLAUDE.md` § "Current state vs. roadmap".

It is also an AgentCulture mesh agent (suffix `xteink`), scaffolded from
`culture-agent-template`. It follows the sibling pattern every Culture agent
uses: an agent-first CLI, a mesh identity, the canonical skill kit, and a
buildable/deployable package baseline. It is a sibling to
[`guildmaster`](https://github.com/agentculture/guildmaster) (the skills
supplier), [`steward`](https://github.com/agentculture/steward) (alignment),
and [`teken`](https://github.com/agentculture/teken) (the CLI scaffolder this
package is cited from).

## Four harnesses, four files, no shared base

This repo's root carries one prompt file per harness, each read by exactly
one of them — there is deliberately no shared `AGENTS.md` base for them to
cascade from:

- **Claude Code** reads [`CLAUDE.md`](CLAUDE.md).
- **Pi / associate** reads this file (`AGENTS.override.md`) for context, plus
  [`.pi/SYSTEM.md`](.pi/SYSTEM.md) for its system prompt.
- **colleague** reads [`AGENTS.colleague.md`](AGENTS.colleague.md) (the start
  of colleague's own cascade — see that file).
- **Qwen Code** reads [`QWEN.md`](QWEN.md).

If you are reading this as a human, `CLAUDE.md` is the fullest write-up of the
repo's conventions and is the one to read first; the other three exist to keep
each non-Claude harness from silently inheriting Claude-specific instructions
it cannot act on the same way.

## Identity

Declared in `culture.yaml`:

```yaml
agents:
- suffix: xteink
  backend: claude
```

This agent's *mesh* resident runs on `backend: claude`, so `CLAUDE.md` is
the live resident prompt. A Pi session working in a clone of this repo is a
**local tool session**, not the mesh resident — it reads this file and
`.pi/SYSTEM.md` regardless of what `culture.yaml` declares, and running `pi`
here neither requires nor changes that declaration.

(A clone that wants `associate` as its *mesh* resident declares
`backend: colleague` with `model: associate` — see `docs/skill-sources.md`.
That is a per-clone choice; this repo does not use it.)

## Layout (what you can read/find/summarize here)

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

## Conventions worth knowing before you answer a question about this repo

- The vendored skills under `.claude/skills/` are cited **verbatim** from
  guildmaster — never propose editing their scripts; the fix belongs upstream
  (`docs/skill-sources.md` has the re-sync procedure).
- The package/CLI name `xteink` is hard-coded in roughly a hundred places, so
  a rename is a `git grep -nF xteink` sweep, not a hand edit.
- Every PR bumps the version (`version-bump` skill); CI's `version-check` job
  blocks merge otherwise.
- This file describes the repo **as it exists on disk today**. If you are
  asked to update it, keep claims grounded in checked-in reality.
