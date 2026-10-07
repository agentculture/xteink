"""Tests for the API-client nouns: server, library, device, tunnel, mcp."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from tests.cli.conftest import KEY
from xteink.cli import main
from xteink.explain import known_paths

NOUNS = {
    "server": ["status"],
    "library": ["add", "list", "rm"],
    "device": ["list", "queue", "revoke", "backup", "provision"],
    "tunnel": ["status", "plan"],
    "mcp": ["serve"],
}


def run(capsys, argv):
    rc = main(argv)
    cap = capsys.readouterr()
    return rc, cap.out, cap.err


# --- criterion 1: overview / json / explain ---------------------------------


@pytest.mark.parametrize("noun", NOUNS)
def test_overview_verb_text_and_json(capsys, noun):
    rc, out, _ = run(capsys, [noun, "overview"])
    assert rc == 0
    assert f"# xteink {noun}" in out
    rc, out, _ = run(capsys, [noun, "overview", "--json"])
    payload = json.loads(out)
    assert rc == 0
    assert payload["subject"] == f"xteink {noun}"
    items = " ".join(i for s in payload["sections"] for i in s["items"])
    for verb in NOUNS[noun]:
        assert verb in items
    rc, out, _ = run(capsys, [noun])  # bare noun == overview
    assert rc == 0
    assert f"# xteink {noun}" in out


def test_explain_entries_exist(capsys):
    paths = set(known_paths())
    for noun, verbs in NOUNS.items():
        for p in [(noun,), (noun, "overview"), *[(noun, v) for v in verbs]]:
            assert p in paths, p
            rc, out, _ = run(capsys, ["explain", *p])
            assert rc == 0
            assert out.strip()


# --- read verbs ---------------------------------------------------------------


def test_library_list_text_and_json(api, capsys):
    rc, out, _ = run(capsys, ["library", "list", "--q", "dune", "--kind", "book", "--limit", "5"])
    assert rc == 0
    assert "Dune" in out
    assert any("q=dune" in p and "kind=book" in p and "limit=5" in p for _, p in api.requests)
    rc, out, _ = run(capsys, ["library", "list", "--json"])
    assert [i["id"] for i in json.loads(out)["items"]] == [1, 2]


def test_device_list(api, capsys):
    rc, out, _ = run(capsys, ["device", "list"])
    assert rc == 0
    assert "Reader One" in out
    rc, out, _ = run(capsys, ["device", "list", "--json"])
    assert len(json.loads(out)["devices"]) == 2


def test_server_status(api, capsys):
    rc, out, err = run(capsys, ["server", "status", "--json"])
    rep = json.loads(out)
    assert rc == 0
    assert rep["server"]["reachable"] is True
    assert rep["api_key"]["valid"] is True
    assert rep["device_app"]["status"] == "alive"
    assert KEY not in out + err


def test_server_status_bad_key_and_unreachable(api, capsys, monkeypatch):
    monkeypatch.setenv("XTEINK_API_KEY", "wrong")
    rc, out, _ = run(capsys, ["server", "status", "--json"])
    assert rc == 1
    assert json.loads(out)["api_key"]["valid"] is False
    monkeypatch.setenv("XTEINK_URL", "http://127.0.0.1:1")
    rc, out, _ = run(capsys, ["server", "status", "--json"])
    assert rc == 2
    assert json.loads(out)["server"]["reachable"] is False


def test_missing_key_is_environment_error(capsys, monkeypatch):
    monkeypatch.delenv("XTEINK_API_KEY", raising=False)
    rc, out, err = run(capsys, ["library", "list"])
    assert rc == 2
    assert err.startswith("error:")
    assert "hint:" in err
    assert out == ""


def test_unreachable_is_environment_error(capsys, monkeypatch):
    monkeypatch.setenv("XTEINK_URL", "http://127.0.0.1:1")
    monkeypatch.setenv("XTEINK_API_KEY", KEY)
    rc, _, err = run(capsys, ["device", "list"])
    assert rc == 2
    assert "hint:" in err


def test_api_4xx_is_user_error(api, capsys):
    rc, _, err = run(capsys, ["library", "rm", "99"])
    assert rc == 1
    assert err.startswith("error:")
    rc, out, _ = run(capsys, ["library", "list", "--json"])
    assert KEY not in out


# --- criterion 2: mutating verbs are dry-run unless --apply -------------------


def test_library_add_dry_run_no_write(api, capsys, tmp_path):
    f = tmp_path / "b.epub"
    f.write_bytes(b"PK data")
    rc, out, _ = run(
        capsys, ["library", "add", str(f), "--title", "T", "--device", "reader two", "--json"]
    )
    rep = json.loads(out)
    assert rc == 0
    assert rep["applied"] is False
    assert rep["device"]["name"] == "Reader Two"
    assert api.writes == []
    rc, out, _ = run(capsys, ["library", "add", str(f)])
    assert "would" in out.lower()
    assert "--apply" in out
    assert api.writes == []


def test_library_add_apply_uploads_and_queues(api, capsys, tmp_path):
    f = tmp_path / "b.epub"
    f.write_bytes(b"PK data")
    rc, out, _ = run(capsys, ["library", "add", str(f), "--device", "2", "--apply", "--json"])
    rep = json.loads(out)
    assert rc == 0
    assert rep["applied"] is True
    assert rep["item"]["id"] == 1
    assert api.writes == [("POST", "/api/library"), ("POST", "/api/devices/2/queue")]


def test_library_add_bad_path_and_bad_device(api, capsys, tmp_path):
    rc, _, err = run(capsys, ["library", "add", str(tmp_path / "nope.epub")])
    assert rc == 1
    assert "hint:" in err
    f = tmp_path / "b.epub"
    f.write_bytes(b"x")
    rc, _, err = run(capsys, ["library", "add", str(f), "--device", "ghost", "--apply"])
    assert rc == 1
    assert api.writes == []


def test_library_rm_dry_run_then_apply(api, capsys):
    rc, out, _ = run(capsys, ["library", "rm", "1"])
    assert rc == 0
    assert "Dune" in out
    assert "--apply" in out
    assert api.writes == []
    rc, out, _ = run(capsys, ["library", "rm", "1", "--apply", "--json"])
    assert json.loads(out)["applied"] is True
    assert api.writes == [("DELETE", "/api/library/1")]


def test_device_queue_dry_run_then_apply(api, capsys):
    rc, out, _ = run(capsys, ["device", "queue", "Reader One", "2", "--json"])
    rep = json.loads(out)
    assert rc == 0
    assert rep["applied"] is False
    assert rep["device"]["name"] == "Reader One"
    assert rep["item"]["title"] == "Essay"
    assert api.writes == []
    rc, out, _ = run(capsys, ["device", "queue", "Reader One", "2", "--apply"])
    assert rc == 0
    assert api.writes == [("POST", "/api/devices/1/queue")]


def test_device_revoke_dry_run_then_apply(api, capsys):
    rc, out, _ = run(capsys, ["device", "revoke", "reader one"])
    assert rc == 0
    assert "Reader One" in out
    assert "--apply" in out
    assert api.writes == []
    rc, out, _ = run(capsys, ["device", "revoke", "1", "--apply", "--json"])
    assert json.loads(out)["applied"] is True
    assert api.writes == [("POST", "/api/devices/1/revoke")]


# --- tunnel ---------------------------------------------------------------------


def test_tunnel_plan_prints_two_commands(capsys):
    rc, out, _ = run(capsys, ["tunnel", "plan", "--allow", "me@example.com"])
    assert rc == 0
    assert (
        "cultureflare remote-login setup --hostname ebooks.culture.dev "
        "--service http://127.0.0.1:8780 --allow me@example.com --shushu"
    ) in out
    assert (
        "cultureflare remote-login setup --hostname xteink.culture.dev "
        "--service http://127.0.0.1:8781 --no-access --shushu"
    ) in out
    assert "dry-run" in out
    assert "--apply" in out
    rc, out, _ = run(capsys, ["tunnel", "plan", "--json", "--ui-host", "a.example"])
    rep = json.loads(out)
    assert len(rep["commands"]) == 2
    assert "a.example" in rep["commands"][0]


def test_tunnel_status_uses_injected_probe(capsys, monkeypatch):
    from xteink.cli._commands import tunnel

    seen = []

    def fake(url, timeout=5.0):
        seen.append(url)
        if "xteink.culture.dev" in url:
            return 401, ""
        return 302, ""

    monkeypatch.setattr(tunnel, "probe", fake)
    rc, out, _ = run(capsys, ["tunnel", "status", "--json"])
    rep = json.loads(out)
    assert rc == 0
    assert rep["ui"]["status"] == "reachable"
    assert rep["device"]["status"] == "reachable"
    assert seen == [
        "https://ebooks.culture.dev/",
        "https://xteink.culture.dev/api/device/whoami",
    ]


def test_tunnel_status_down_never_fails_hard_unless_strict(capsys, monkeypatch):
    from xteink.cli._commands import tunnel

    monkeypatch.setattr(tunnel, "probe", lambda url, timeout=5.0: (None, "refused"))
    rc, out, _ = run(capsys, ["tunnel", "status", "--json"])
    assert rc == 0
    assert json.loads(out)["ui"]["status"] == "unreachable"
    rc, _, _ = run(capsys, ["tunnel", "status", "--strict"])
    assert rc == 2
    monkeypatch.setattr(tunnel, "probe", lambda url, timeout=5.0: (200, ""))
    rc, out, _ = run(capsys, ["tunnel", "status", "--json"])
    assert rc == 0
    assert json.loads(out)["ui"]["status"] == "unexpected"


# --- mcp --------------------------------------------------------------------------


def test_mcp_serve_delegates(capsys, monkeypatch):
    import xteink.mcp.__main__ as mcp_main

    calls = []
    monkeypatch.setattr(mcp_main, "main", lambda argv=None, env=None: calls.append(argv) or 0)
    rc, _, _ = run(capsys, ["mcp", "serve", "--http", "--port", "9"])
    assert rc == 0
    assert calls == [["--http", "--port", "9"]]


# --- criterion 3: import hygiene -----------------------------------------------------


def _imports(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                yield node, a.name
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            yield node, base
            for a in node.names:
                yield node, f"{base}.{a.name}"


def test_cli_never_imports_core_or_server():
    root = Path(__file__).resolve().parents[2] / "xteink" / "cli"
    bad = []
    for py in root.rglob("*.py"):
        for _, name in _imports(ast.parse(py.read_text())):
            if name in ("xteink.core", "xteink.server") or name.startswith(
                ("xteink.core.", "xteink.server.")
            ):
                bad.append((py.name, name))
    assert bad == []


def test_only_mcp_module_imports_xteink_mcp_and_lazily():
    root = Path(__file__).resolve().parents[2] / "xteink" / "cli"
    for py in root.rglob("*.py"):
        tree = ast.parse(py.read_text())
        for node in tree.body:  # module level only
            for _, name in (
                _imports(ast.Module(body=[node], type_ignores=[]))
                if isinstance(node, (ast.Import, ast.ImportFrom))
                else []
            ):
                assert not name.startswith(("xteink.mcp", "mcp")), (py.name, name)
