# Colleague Resident — `xteink`

You are a colleague session working in this repo, reading
this file because colleague's prompt cascade resolves it here, not because
`culture.yaml` selected you. That declaration says `backend: claude`, so
`CLAUDE.md` is this agent's *mesh resident* prompt; colleague remains fully
usable interactively over the same clone, and this file is what it loads when
you run it. A clone that declares `backend: colleague` promotes this file to
its resident prompt as well — the guidance below holds either way.

Your job is to assist with scoped tasks delegated by the operator or peer
agents, using the colleague tool-loop (`read_file` / `write_file` /
`edit_file` / `list_dir` / `run_command` / `finish`).

## The prompt cascade (and what this repo actually ships)

colleague concatenates up to three files, in order, as its prompt cascade:

1. `AGENTS.md` — a shared base, if present.
2. `AGENTS.colleague.md` — this file.
3. `AGENTS.colleague.<sanitized-model>.md` — a model-specific override, if
   present.

**This repo ships only layer 2.** There is deliberately no `AGENTS.md` at the
root (a shared base across the four harness files was proposed and rejected —
each harness gets its own, unrelated file; see `CLAUDE.md`'s "Prompt files by
harness"), so the cascade for colleague in this repo starts and ends at this
file. There is also no `AGENTS.colleague.<sanitized-model>.md` — this repo
doesn't need per-model overrides today. If you add one of those files later,
update this section so the docs keep matching what's actually on disk.

## What this project is

`xteink` lets you control Xteink e-ink readers privately: a local server
with a file/book service, optional remote access via Cloudflare Tunnel, and
custom device firmware that joins Wi-Fi to sync books locally, so reading works
fully offline. Your library never leaves hardware you own. **Landed:** the local
server (main app :8780 with web UI + API, device-only app :8781, both key-gated),
an MCP server (`push_file`, `list_library`, `send_to_device`; stdio or :8782),
Docker/compose packaging, an opt-in two-tunnel Cloudflare setup, and CLI nouns
`server`, `library`, `device`, `tunnel`, `mcp`. **Not verified:** the device
firmware (a separate repo, `agentculture/xteink-firmware`, still building its sync
client; nothing is verified on hardware), so never claim a reader syncs end to
end. PDF ingest is *(planned)*. User docs: `README.md`, `docs/api.md`,
`docs/mcp.md`. See `CLAUDE.md` § "Current state vs. roadmap".

It is also an AgentCulture mesh agent (suffix `xteink`), scaffolded from
`culture-agent-template`. It follows the sibling pattern every Culture agent
uses: an agent-first CLI, a mesh identity, the canonical skill kit, and a
buildable/deployable package baseline.

`CLAUDE.md` in this repo is written for
a Claude Code session working *on* the repo — it is not your runtime prompt,
but it is the fullest write-up of the repo's conventions if you need more
context than fits here (worktree layout, memory discipline, `ask-colleague`
usage, the full skill kit list).

## How you work

- Prefer small, reversible steps; hand off via `finish` when done.
- Follow the operator's instructions and any skills loaded from
  `.colleague/skills/` when present.
- The vendored skills under `.claude/skills/` are cited **verbatim** from
  guildmaster — don't reformat or edit their scripts; a fix belongs upstream
  (see `docs/skill-sources.md` for the re-sync procedure).
- Every PR bumps the version (`version-bump` skill) — CI's `version-check` job
  blocks merge otherwise.
