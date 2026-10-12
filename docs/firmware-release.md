# Firmware release flow

`scripts/firmware-release.py` is the agent's release flow for the Xteink reader
firmware. It takes a **merged** pull request on the firmware fork
(`agentculture/xteink-firmware`), builds the merge commit, uploads the image to
the xteink server, offers it over the air to every device, and comments on the
PR. It is stdlib-only and is not a vendored skill.

It never invokes esptool and never opens a serial port. Devices receive the
image over Wi-Fi: the server offers it and the device pulls it. A test asserts
this on both the script source and every command it runs.

## Release

```bash
python3 scripts/firmware-release.py release PR_NUMBER \
  [--integration-branch BRANCH] [--fork-checkout PATH] \
  [--pio-env xteink_release] [--pio PATH] [--version V] [--fork OWNER/REPO] \
  [--key-name SECRET] [--no-grant]
```

Order of operations:

1. `gh -R <fork> pr view` must show `MERGED`, merged into the integration
   branch, with every check green (at least one check must exist).
2. `git fetch` the integration branch in the fork checkout, then verify the
   merge commit is an ancestor of `origin/<integration-branch>`.
3. Refuse if an image already uploaded for that commit was rolled back on any
   device (`xteink firmware list`, then `xteink firmware rollbacks`).
4. `git worktree add --detach` the merge commit in a temp directory, then
   `git submodule update --init freeink-sdk`. The tree must be clean.
5. `pio run -e xteink_release`, which builds the ESP32-C3 image shared by the X3 and
   X4 at `.pio/build/xteink_release/firmware.bin`. Its version is
   `<base>+xteink.<fork sha8>`, so every build is distinct to the device's
   install decision (upstream's `gh_release` env gives every build the same bare version). The tree must still be clean.
6. `xteink firmware upload IMAGE --commit SHA --pr URL --apply`.
7. `xteink firmware offer ID --all --apply`.
8. `gh pr comment` on the fork PR with the version, fork sha and the devices
   offered. The body is signed `- xteink (Claude)` through the cicd skill's
   `pr-reply.sh --print-body`, which resolves the nick from `culture.yaml`.
9. The temp worktree is always removed (submodules deinitialised first).

Any refusal in steps 1 to 5 exits `1` with nothing uploaded or offered. A tool
that fails or is missing exits `2`.

Each `xteink` call runs under `grant run --inject
XTEINK_API_KEY=XTEINK_MCP_API_KEY --`, so the admin key never touches a file or
the output. Use `--no-grant` when `XTEINK_API_KEY` is already in the environment,
and `--key-name` (or `XTEINK_GRANT_KEY`) for a differently named grant secret.

### Configuration

| Setting | Flag | Environment | Default |
|---------|------|-------------|---------|
| Integration branch | `--integration-branch` | `XTEINK_INTEGRATION_BRANCH` | `feat/issue-1` |
| Fork checkout | `--fork-checkout` | `XTEINK_FORK_CHECKOUT` | `~/git/xteink-firmware` |
| Admin key secret | `--key-name` | `XTEINK_GRANT_KEY` | `XTEINK_MCP_API_KEY` |
| PlatformIO binary | `--pio` | `PIO` | `penv/bin/pio` in PlatformIO's default home |

The integration branch is configuration, not a constant: today it is the fork's
`feat/issue-1`, and it will probably become the default branch.

## Reporting rollbacks

```bash
python3 scripts/firmware-release.py report-rollbacks [--dry-run]
```

A device that boots a new image and rolls back reports it on its next run, and
the server records it (`GET /api/firmware/{id}/rollbacks`, `xteink firmware
rollbacks`). This subcommand lists every uploaded image that has a `source_pr`
and a rollback, and comments once per rollback on the PR that shipped it. Each
comment carries a hidden marker, `<!-- xteink-rollback device=ID fw=SHA -->`, and
a rollback whose marker is already on the PR is skipped, so it is safe to run on
a schedule.
