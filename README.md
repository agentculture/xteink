# xteink

Control Xteink e-ink readers privately: a local server with a file/book service, optional remote access via Cloudflare Tunnel, and custom device firmware that joins Wi-Fi to sync books locally so reading works fully offline. Your library never leaves hardware you own.

## Status

**Early scaffold.** The e-ink pieces are planned, not built yet:

- **(planned)** Local server with a file/book service the readers sync from.
- **(planned)** Optional remote access through Cloudflare Tunnel.
- **(planned)** Custom Xteink firmware that joins Wi-Fi and syncs books over the
  local network, so reading needs no cloud.

What ships today is the agent scaffold below: the CLI, the mesh identity,
the harness prompts, the skill kit, and CI/CD.

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

## Quickstart

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
