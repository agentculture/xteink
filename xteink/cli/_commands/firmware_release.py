"""``xteink firmware release`` / ``report-rollbacks`` — the agent's firmware release flow.

``release PR`` takes a merged fork PR to the devices: checks it, builds its merge commit,
uploads the image, offers it to every device and comments on the PR. ``report-rollbacks``
comments once on the fork PR that shipped a build a device rolled back.

Every external command (gh, git, pio, xteink, grant) goes through ``_run`` so tests stub it.
This flow never invokes esptool and never opens a serial port: devices get the image over the
air (the server offers it; the device pulls it). See docs/firmware-release.md.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess  # nosec B404 - runs fixed argv lists, never a shell
import sys
import tempfile
from pathlib import Path
from typing import Any, Sequence

from xteink.cli._commands.server import add_json, json_mode
from xteink.cli._errors import EXIT_ENV_ERROR, EXIT_USER_ERROR, CliError
from xteink.cli._output import emit_result

REPO_ROOT = Path(__file__).resolve().parents[3]
FORK_REPO = "agentculture/xteink-firmware"
DEFAULT_FORK_CHECKOUT = Path.home() / "git" / "xteink-firmware"
DEFAULT_PIO_ENV = "xteink_release"
DEFAULT_PIO = Path.home() / ".platformio" / "penv" / "bin" / "pio"
PR_REPLY = REPO_ROOT / ".claude" / "skills" / "cicd" / "scripts" / "pr-reply.sh"
# The xteink calls run this same install (not whatever `xteink` is first on PATH).
XTEINK_CMD = (sys.executable, "-m", "xteink")
GREEN_CONCLUSIONS = {"SUCCESS", "NEUTRAL", "SKIPPED"}
ROLLBACK_MARKER = "<!-- xteink-rollback device={device} fw={sha} -->"


def refused(message: str) -> CliError:
    """A release precondition failed; nothing was uploaded or offered (exit 1)."""
    return CliError(EXIT_USER_ERROR, f"refused: {message}", "fix the precondition and re-run")


def env_failure(message: str) -> CliError:
    """An external tool failed or is missing (exit 2)."""
    return CliError(EXIT_ENV_ERROR, message, "check the tool named above, then re-run")


def _run(
    cmd: Sequence[str], *, cwd: str | Path | None = None, input_text: str | None = None
) -> subprocess.CompletedProcess:
    """The single place a subprocess starts. Tests replace this."""
    try:
        return subprocess.run(  # nosec B603 - fixed argv list, shell=False
            list(cmd), cwd=cwd, input=input_text, capture_output=True, text=True, check=False
        )
    except FileNotFoundError as exc:
        raise env_failure(f"{cmd[0]} not found on PATH") from exc
    except OSError as exc:  # not executable, cwd not a directory, ...
        raise env_failure(f"{cmd[0]} could not be started: {exc}") from exc


def _ok(cmd: Sequence[str], *, cwd: str | Path | None = None, input_text: str | None = None) -> str:
    res = _run(cmd, cwd=cwd, input_text=input_text)
    if res.returncode != 0:
        tail = (res.stderr or res.stdout or "").strip().splitlines()[-3:]
        raise env_failure(f"{' '.join(cmd[:3])} failed (exit {res.returncode}): {' | '.join(tail)}")
    return res.stdout


def _json(cmd: Sequence[str], **kw: Any) -> Any:
    out = _ok(cmd, **kw)
    try:
        return json.loads(out)
    except json.JSONDecodeError as exc:
        raise env_failure(f"{' '.join(cmd[:3])} did not print JSON") from exc


def _xteink(args: argparse.Namespace, *sub: str) -> list[str]:
    """An xteink invocation, with the admin key injected from grant unless --no-grant."""
    cmd = [*XTEINK_CMD, *sub, "--json"]
    if args.no_grant:
        return cmd
    return ["grant", "run", "--inject", f"XTEINK_API_KEY={args.key_name}", "--", *cmd]


def _log(msg: str) -> None:
    print(f"firmware release: {msg}", file=sys.stderr)


# --- release -------------------------------------------------------------------------


def check_pr(args: argparse.Namespace) -> tuple[str, str]:
    """Return (merge sha, PR url); refuse unless merged into the integration branch, green."""
    pr = _json(
        [
            "gh",
            "-R",
            args.fork,
            "pr",
            "view",
            str(args.pr),
            "--json",
            "state,baseRefName,mergeCommit,statusCheckRollup,url",
        ]
    )
    if pr.get("state") != "MERGED":
        raise refused(f"PR #{args.pr} is {pr.get('state')}, not MERGED")
    if pr.get("baseRefName") != args.integration_branch:
        raise refused(
            f"PR #{args.pr} merged into {pr.get('baseRefName')!r}, "
            f"not the integration branch {args.integration_branch!r}"
        )
    sha = (pr.get("mergeCommit") or {}).get("oid")
    if not sha:
        raise refused(f"PR #{args.pr} has no merge commit")
    checks = pr.get("statusCheckRollup") or []
    if not checks:
        raise refused(f"PR #{args.pr} has no checks; refusing to ship an unverified build")
    bad = [
        c.get("name") or c.get("context") or "?"
        for c in checks
        if (c.get("conclusion") or c.get("state") or "").upper() not in GREEN_CONCLUSIONS
    ]
    if bad:
        raise refused(f"PR #{args.pr} checks not green: {', '.join(sorted(bad))}")
    return sha, pr.get("url") or f"https://github.com/{args.fork}/pull/{args.pr}"


def check_on_branch(args: argparse.Namespace, sha: str) -> None:
    repo = str(args.fork_checkout)
    _ok(["git", "-C", repo, "fetch", "origin", args.integration_branch])
    res = _run(
        ["git", "-C", repo, "merge-base", "--is-ancestor", sha, f"origin/{args.integration_branch}"]
    )
    if res.returncode != 0:
        raise refused(f"commit {sha[:12]} is not on origin/{args.integration_branch}")


def check_not_rolled_back(args: argparse.Namespace, sha: str) -> None:
    """Refuse when an already-uploaded image of this commit was rolled back on any device."""
    items = _json(_xteink(args, "firmware", "list"))["firmware"]
    for fw in items:
        if fw.get("fork_commit") != sha:
            continue
        rows = _json(_xteink(args, "firmware", "rollbacks", str(fw["id"])))["rollbacks"]
        if rows:
            names = ", ".join(r["device_name"] for r in rows)
            raise refused(
                f"firmware {fw['id']} ({fw['version']}, {sha[:12]}) was rolled back on: {names}"
            )


def check_clean(tree: Path) -> None:
    out = _ok(["git", "-C", str(tree), "status", "--porcelain"])
    if out.strip():
        raise refused(f"working tree {tree} is dirty:\n{out.strip()}")


def build(args: argparse.Namespace, tree: Path) -> Path:
    _ok(["git", "-C", str(tree), "submodule", "update", "--init", "freeink-sdk"])
    check_clean(tree)
    _ok([str(args.pio), "run", "-e", args.pio_env], cwd=tree)
    image = tree / ".pio" / "build" / args.pio_env / "firmware.bin"
    if not image.is_file():
        raise env_failure(f"build produced no {image}")
    check_clean(tree)  # a build must not modify tracked files
    return image


def cleanup(args: argparse.Namespace, tree: Path, tmp: Path) -> None:
    repo = str(args.fork_checkout)
    if tree.exists():
        _run(["git", "-C", str(tree), "submodule", "deinit", "--all", "--force"])
        status = _run(["git", "-C", str(tree), "status", "--porcelain"])
        if status.returncode == 0 and status.stdout.strip():
            _log(f"warning: removing worktree with changes:\n{status.stdout.strip()}")
        _run(["git", "-C", repo, "worktree", "remove", "--force", str(tree)])
    _run(["git", "-C", repo, "worktree", "prune"])
    shutil.rmtree(tmp, ignore_errors=True)


def signed(body: str) -> str:
    """Append the agent signature through the cicd skill (falls back to a plain signature)."""
    res = _run(["bash", str(PR_REPLY), "--print-body", "0", "0", body])
    if res.returncode == 0 and res.stdout.strip():
        return res.stdout.rstrip("\n")
    _log(f"warning: {PR_REPLY} unavailable (not a source checkout?); signing as xteink")
    return f"{body}\n\n- xteink (Claude)"


def post_comment(fork: str, pr: str, body: str) -> None:
    _ok(["gh", "-R", fork, "pr", "comment", str(pr), "--body-file", "-"], input_text=signed(body))


def device_names(args: argparse.Namespace, ids: list[int]) -> list[str]:
    try:
        devices = _json(_xteink(args, "device", "list"))["devices"]
    except (CliError, KeyError) as exc:
        _log(f"warning: device names unavailable ({exc}); the PR comment lists ids only")
        devices = []
    names = {d.get("id"): d.get("name", "") for d in devices}
    return [f"{names[i]} (#{i})" if names.get(i) else f"#{i}" for i in ids]


def cmd_release(args: argparse.Namespace) -> None:
    sha, pr_url = check_pr(args)
    check_on_branch(args, sha)
    check_not_rolled_back(args, sha)
    repo = str(args.fork_checkout)
    tmp = Path(tempfile.mkdtemp(prefix="xteink-fw-release-"))
    tree = tmp / "fork"
    stage = "build"
    try:
        _ok(["git", "-C", repo, "worktree", "add", "--detach", str(tree), sha])
        check_clean(tree)
        image = build(args, tree)
        extra = ["--version", args.fw_version] if args.fw_version else []
        up_cmd = _xteink(
            args,
            *("firmware", "upload", str(image), "--commit", sha, "--pr", pr_url),
            *extra,
            "--apply",
        )
        up = _json(up_cmd)
        stage = "upload"  # from here on the server may hold (or offer) the image
        uploaded = up["firmware"]
        if not up.get("created", True) and uploaded.get("fork_commit") != sha:
            # Identical bytes are already stored under another commit's row: offering it
            # would credit this PR in the comment while rollback bookkeeping stays on that one.
            owner = uploaded.get("fork_commit")
            raise CliError(
                EXIT_USER_ERROR,
                f"refused: the build is byte-identical to firmware {uploaded['id']} "
                f"({uploaded['version']}), stored "
                + (f"for commit {owner[:12]}" if owner else "without a fork commit")
                + "; nothing was offered",
                f"this PR changed no firmware bytes; to ship that image anyway run "
                f"'xteink firmware offer {uploaded['id']} --all --apply'",
            )
        offered = _json(_xteink(args, "firmware", "offer", str(uploaded["id"]), "--all", "--apply"))
        stage = "offer"
        ids = [int(i) for i in offered["offered"]]
        who = ", ".join(device_names(args, ids)) or "none"
        body = (
            f"Firmware released over the air.\n\n"
            f"- version: `{uploaded['version']}`\n"
            f"- fork commit: `{sha}`\n"
            f"- devices offered: {who}\n"
            f"- skipped (revoked): {len(offered.get('skipped_revoked', []))}, "
            f"skipped (rolled back): {len(offered.get('skipped_rolled_back', []))}"
        )
        post_comment(args.fork, str(args.pr), body)
    except CliError:
        raise
    except Exception as exc:  # noqa: BLE001 - an unexpected shape after a side effect
        raise CliError(
            EXIT_ENV_ERROR,
            f"release failed after the {stage} step: {exc.__class__.__name__}: {exc}",
            "the image may already be stored or offered: check 'xteink firmware list' and "
            "'xteink device list' before re-running",
        ) from exc
    finally:
        cleanup(args, tree, tmp)
    payload = {"version": uploaded["version"], "sha": sha, "offered": ids}
    text = f"released {uploaded['version']} ({sha[:12]}) to {who}; commented on PR #{args.pr}"
    emit_result(payload if json_mode(args) else text, json_mode=json_mode(args))


# --- rollback report -----------------------------------------------------------------


def _pr_ref(url: str) -> tuple[str, str] | None:
    m = re.match(r"https?://github\.com/([^/]+/[^/]+)/pull/(\d+)", url or "")
    return (m.group(1), m.group(2)) if m else None


def _rollback_body(marker: str, fw: dict[str, Any], row: dict[str, Any]) -> str:
    return (
        f"{marker}\n"
        f"Device **{row['device_name']}** (#{row['device_id']}) rolled back firmware "
        f"`{fw['version']}` (fork commit `{fw['fork_commit']}`) at "
        f"{row['rolled_back_at']}. It will not be offered this build again."
    )


def _report_image(args: argparse.Namespace, fw: dict[str, Any]) -> list[str]:
    """Comment once per not-yet-reported rollback of one image; return one line per comment."""
    ref = _pr_ref(fw.get("source_pr") or "")
    if not ref or not fw.get("fork_commit"):
        return []
    rows = _json(_xteink(args, "firmware", "rollbacks", str(fw["id"])))["rollbacks"]
    if not rows:
        return []
    repo, pr = ref
    view = _json(["gh", "-R", repo, "pr", "view", pr, "--json", "comments"])
    existing = "\n".join(c.get("body", "") for c in view.get("comments", []))
    lines = []
    for row in rows:
        marker = ROLLBACK_MARKER.format(device=row["device_id"], sha=fw["fork_commit"])
        if marker in existing:
            continue
        if args.dry_run:
            lines.append(f"would comment on {repo}#{pr}: device {row['device_id']}")
        else:
            post_comment(repo, pr, _rollback_body(marker, fw, row))
            lines.append(f"commented on {repo}#{pr}: device {row['device_id']}")
    return lines


def cmd_report_rollbacks(args: argparse.Namespace) -> None:
    lines: list[str] = []
    for fw in _json(_xteink(args, "firmware", "list"))["firmware"]:
        lines.extend(_report_image(args, fw))
    payload = {"commented": len(lines), "dry_run": bool(args.dry_run)}
    text = "\n".join(lines) or "no new rollbacks to report"
    emit_result(payload if json_mode(args) else text, json_mode=json_mode(args))


# --- parser --------------------------------------------------------------------------


def _common(sp: argparse.ArgumentParser) -> None:
    sp.add_argument("--fork", default=FORK_REPO, help="Fork repo (OWNER/REPO).")
    sp.add_argument(
        "--key-name",
        default=os.environ.get("XTEINK_GRANT_KEY", "XTEINK_MCP_API_KEY"),
        help="grant secret holding the admin key (env XTEINK_GRANT_KEY).",
    )
    sp.add_argument("--no-grant", action="store_true", help="XTEINK_API_KEY is already in the env.")
    add_json(sp)


def register_release(nsub: argparse._SubParsersAction) -> None:
    """Add ``release`` and ``report-rollbacks`` under the ``firmware`` noun."""
    r = nsub.add_parser("release", help="Ship a merged fork PR over the air.")
    r.add_argument("pr", type=int, metavar="PR_NUMBER", help="Merged fork PR number.")
    r.add_argument(
        "--integration-branch",
        default=os.environ.get("XTEINK_INTEGRATION_BRANCH", "feat/issue-1"),
        help="Branch the PR must be merged into (env XTEINK_INTEGRATION_BRANCH).",
    )
    r.add_argument(
        "--fork-checkout",
        type=Path,
        default=Path(os.environ.get("XTEINK_FORK_CHECKOUT", DEFAULT_FORK_CHECKOUT)),
        help="Local clone of the fork (env XTEINK_FORK_CHECKOUT); a temp worktree is added to it.",
    )
    r.add_argument("--pio-env", default=DEFAULT_PIO_ENV, help="PlatformIO env to build.")
    r.add_argument("--pio", type=Path, default=Path(os.environ.get("PIO", DEFAULT_PIO)))
    r.add_argument(
        "--version",
        dest="fw_version",
        help="Only if the image carries no version string.",
    )
    _common(r)
    r.set_defaults(func=cmd_release)

    rr = nsub.add_parser("report-rollbacks", help="Comment once per rollback on the shipping PR.")
    rr.add_argument("--dry-run", action="store_true", help="Print what would be commented.")
    _common(rr)
    rr.set_defaults(func=cmd_report_rollbacks)
