"""`xteink firmware release` / `report-rollbacks` with every external command stubbed.

No gh, git, pio or device is touched.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from xteink.cli import main
from xteink.cli._commands import firmware_release as fr

SOURCE = Path(fr.__file__)
SHA = "a" * 40
PR_URL = "https://github.com/agentculture/xteink-firmware/pull/7"


def cp(out="", rc=0, err=""):
    return subprocess.CompletedProcess([], rc, out, err)


class Fake:
    """Records every command; answers from a table keyed by recognisable argv fragments."""

    def __init__(self, tmp_path, **over):
        self.calls: list[list[str]] = []
        self.inputs: list[str] = []
        self.tmp = tmp_path
        self.pr = {
            "state": "MERGED",
            "baseRefName": "feat/issue-1",
            "mergeCommit": {"oid": SHA},
            "statusCheckRollup": [{"name": "ci", "conclusion": "SUCCESS"}],
            "url": PR_URL,
        }
        self.dirty = False
        self.on_branch = True
        self.firmware = []  # existing uploaded images
        self.rollbacks: dict[int, list[dict]] = {}
        self.pr_comments: list[dict] = []
        self.__dict__.update(over)

    def names(self):
        return [c[0] if c[0] != "grant" else c[c.index("--") + 1] for c in self.calls]

    def find(self, *frag):
        return [c for c in self.calls if all(f in c for f in frag)]

    def __call__(self, cmd, *, cwd=None, input_text=None):
        cmd = list(cmd)
        self.calls.append(cmd)
        if input_text is not None:
            self.inputs.append(input_text)
        if cmd[0] == "gh" and "view" in cmd:
            if "comments" in cmd[-1]:
                return cp(json.dumps({"comments": self.pr_comments}))
            return cp(json.dumps(self.pr))
        if cmd[0] == "gh" and "comment" in cmd:
            return cp("")
        if cmd[0] == "bash":  # pr-reply.sh --print-body
            return cp(cmd[-1] + "\n\n- xteink (Claude)\n")
        if cmd[0] == "git":
            if "worktree" in cmd and "add" in cmd:
                Path(cmd[cmd.index("add") + 2]).mkdir(parents=True)
            if "merge-base" in cmd:
                return cp(rc=0 if self.on_branch else 1)
            if "status" in cmd:
                return cp(" M foo.c\n" if self.dirty else "")
            return cp("")
        if cmd[-0].endswith("pio"):
            out = Path(cwd) / ".pio" / "build" / "xteink_release"
            out.mkdir(parents=True)
            (out / "firmware.bin").write_bytes(b"\xe9")
            return cp("")
        inner = cmd[cmd.index("--") + 1 :] if cmd[0] == "grant" else cmd
        assert inner[0] == "xteink", cmd
        verb = inner[1:3]
        if verb == ["firmware", "list"]:
            return cp(json.dumps({"firmware": self.firmware}))
        if verb == ["firmware", "rollbacks"]:
            return cp(json.dumps({"rollbacks": self.rollbacks.get(int(inner[3]), [])}))
        if verb == ["firmware", "upload"]:
            fw = {"id": 5, "version": "1.7.0", "fork_commit": SHA}
            return cp(json.dumps({"firmware": fw, "created": True}))
        if verb == ["firmware", "offer"]:
            return cp(
                json.dumps({"offered": [1, 2], "skipped_revoked": [], "skipped_rolled_back": []})
            )
        if verb == ["device", "list"]:
            devs = [{"id": 1, "name": "Reader One"}, {"id": 2, "name": "Reader Two"}]
            return cp(json.dumps({"devices": devs}))
        raise AssertionError(f"unexpected command {cmd}")


@pytest.fixture
def fake(tmp_path, monkeypatch):
    f = Fake(tmp_path)
    monkeypatch.setattr(fr, "_run", f)
    monkeypatch.setattr(fr.tempfile, "mkdtemp", lambda prefix: str(tmp_path / "wt"))
    (tmp_path / "wt").mkdir()
    return f


def release(*extra):
    argv = ["firmware", "release", "7", "--fork-checkout", "/fork", "--pio", "/x/pio", "--json"]
    return main([*argv, *extra])


def report(*extra):
    return main(["firmware", "report-rollbacks", "--json", *extra])


def test_happy_path_order_and_comment(fake, capsys):
    assert release() == 0
    seq = []
    for c in fake.calls:
        if "worktree" in c and "add" in c:
            seq.append("worktree-add")
        elif "submodule" in c and "update" in c:
            seq.append("submodule")
        elif c[0].endswith("pio"):
            seq.append("pio")
        elif "upload" in c:
            seq.append("upload")
        elif "offer" in c:
            seq.append("offer")
        elif c[0] == "gh" and "comment" in c:
            seq.append("comment")
        elif "remove" in c and "worktree" in c:
            seq.append("worktree-remove")
    assert seq == [
        "worktree-add",
        "submodule",
        "pio",
        "upload",
        "offer",
        "comment",
        "worktree-remove",
    ]
    (upload,) = fake.find("upload")
    assert upload[:5] == ["grant", "run", "--inject", "XTEINK_API_KEY=XTEINK_MCP_API_KEY", "--"]
    assert ["--commit", SHA, "--pr", PR_URL, "--apply"] == upload[
        upload.index("--commit") : upload.index("--commit") + 5
    ]
    assert fake.find("offer")[0][-3:] == ["--all", "--apply", "--json"]
    assert fake.find("-e", "xteink_release")
    assert fake.find("-R", "agentculture/xteink-firmware", "comment", "7")
    (body,) = fake.inputs
    assert "1.7.0" in body and SHA in body
    assert "Reader One (#1)" in body and "Reader Two (#2)" in body
    assert body.rstrip().endswith("- xteink (Claude)")
    assert json.loads(capsys.readouterr().out)["offered"] == [1, 2]


def assert_refused_before_upload(fake, rc):
    assert rc == 1  # refused: a precondition failed
    assert not fake.find("upload") and not fake.find("offer")
    assert not [c for c in fake.calls if c[0] == "gh" and "comment" in c]


def test_unmerged_pr(fake):
    fake.pr["state"] = "OPEN"
    assert_refused_before_upload(fake, release())
    assert not fake.find("worktree", "add")


def test_wrong_base_branch(fake):
    fake.pr["baseRefName"] = "main"
    assert_refused_before_upload(fake, release())


def test_integration_branch_is_configurable(fake, monkeypatch):
    fake.pr["baseRefName"] = "main"
    assert release("--integration-branch", "main") == 0
    assert fake.find("fetch", "origin", "main")
    assert fake.find("--is-ancestor", SHA, "origin/main")


@pytest.mark.parametrize(
    "checks",
    [
        [{"name": "ci", "conclusion": "FAILURE"}],
        [{"name": "ci", "conclusion": "SUCCESS"}, {"name": "lint", "conclusion": ""}],
        [],
    ],
)
def test_red_pending_or_missing_checks(fake, checks):
    fake.pr["statusCheckRollup"] = checks
    assert_refused_before_upload(fake, release())


def test_commit_not_on_integration_branch(fake):
    fake.on_branch = False
    assert_refused_before_upload(fake, release())


def test_dirty_tree(fake):
    fake.dirty = True
    assert_refused_before_upload(fake, release())
    assert fake.find("worktree", "remove")


def test_previously_rolled_back_version(fake):
    fake.firmware = [{"id": 3, "version": "1.7.0", "fork_commit": SHA}]
    fake.rollbacks = {3: [{"device_id": 2, "device_name": "Reader Two", "rolled_back_at": "t"}]}
    assert_refused_before_upload(fake, release())
    assert not fake.find("worktree", "add")


def test_other_commits_rollbacks_do_not_block(fake):
    fake.firmware = [{"id": 3, "version": "1.6.0", "fork_commit": "b" * 40}]
    fake.rollbacks = {3: [{"device_id": 2, "device_name": "x", "rolled_back_at": "t"}]}
    assert release() == 0


def test_tool_failure_is_exit_2_and_cleans_up(fake, monkeypatch):
    real = fake.__call__

    def boom(cmd, **kw):
        if cmd[0].endswith("pio"):
            fake.calls.append(list(cmd))
            return cp(rc=1, err="compile error")
        return real(cmd, **kw)

    monkeypatch.setattr(fr, "_run", boom)
    assert release() == 2
    assert not fake.find("upload")
    assert fake.find("worktree", "remove")


def test_no_grant_uses_bare_xteink(fake):
    assert release("--no-grant") == 0
    assert fake.find("upload")[0][0] == "xteink"
    assert not fake.find("grant")


# --- rollback report -----------------------------------------------------------------

FW = {"id": 3, "version": "1.7.0", "fork_commit": SHA, "source_pr": PR_URL}
ROW = {"device_id": 2, "device_name": "Reader Two", "rolled_back_at": "2026-10-11T10:00:00Z"}


def comments(fake):
    return [c for c in fake.calls if c[0] == "gh" and "comment" in c]


def test_rollback_report_comments_once_per_rollback(fake):
    fake.firmware = [FW]
    fake.rollbacks = {3: [ROW, {**ROW, "device_id": 4, "device_name": "Other"}]}
    assert report() == 0
    assert len(comments(fake)) == 2
    assert fr.ROLLBACK_MARKER.format(device=2, sha=SHA) in fake.inputs[0]
    assert "1.7.0" in fake.inputs[0] and "Reader Two" in fake.inputs[0]
    assert fake.inputs[0].rstrip().endswith("- xteink (Claude)")
    # second run: gh now shows both markers -> nothing more is posted
    fake.pr_comments = [{"body": b} for b in fake.inputs]
    fake.calls.clear()
    assert report() == 0
    assert comments(fake) == []


def test_rollback_report_dry_run_and_no_rollbacks(fake):
    fake.firmware = [FW]
    assert report() == 0
    assert comments(fake) == []
    fake.rollbacks = {3: [ROW]}
    assert report("--dry-run") == 0
    assert comments(fake) == []


# --- never touches a device ----------------------------------------------------------

FORBIDDEN = ("esptool", "ttyACM", "ttyUSB", "serial", "upload_port", "-t upload", "pio device")


def test_release_source_has_no_flash_or_serial_access():
    src = SOURCE.read_text().lower()
    code = "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("#"))
    # the module docstring states the rule in words; strip it before scanning
    code = code.split('"""', 2)[2]
    for word in FORBIDDEN:
        assert word.lower() not in code, word


def test_no_flash_or_serial_command_is_ever_run(fake, tmp_path):
    release()
    fake.firmware = [FW]
    fake.rollbacks = {3: [ROW]}
    report()
    flat = " ".join(" ".join(c) for c in fake.calls).lower().replace(str(tmp_path).lower(), "")
    for word in FORBIDDEN:
        assert word.lower() not in flat, word
    pio = fake.find("run", "-e")
    assert pio and all("-t" not in c and "--target" not in c for c in pio)
