"""Tests for ``xteink device backup`` / ``device provision`` (fake esptool, fake serial port).

No real serial device is ever opened: the transport is an in-memory fake (or a pty pair for the
termios implementation) and esptool is a script written into tmp_path.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import sys
import threading
from pathlib import Path

import pytest

from xteink.cli import main
from xteink.cli._commands import device_usb as du

MAC = "AA:BB:CC:DD:EE:FF"
KEY = "xtd_0a1b2c3d_SECRETSECRETsecret"
PASSWORD = "hunter2-wifi-pw"
SIZE = 4096

FAKE_ESPTOOL = f"""#!{sys.executable}
import sys
a = sys.argv[1:]
if "--fail" in a:
    sys.exit(1)
cmd = [x for x in a if x in ("read-mac", "flash-id", "read-flash")][0]
if cmd == "read-mac":
    print("esptool v5\\nMAC: {MAC.lower()}")
elif cmd == "flash-id":
    print("Detected flash size: 4KB")
else:
    i = a.index("read-flash")
    size = int(a[i + 2], 0)
    open(a[i + 3], "wb").write(b"\\xab" * size)
"""


def run(capsys, argv):
    rc = main(argv)
    cap = capsys.readouterr()
    return rc, cap.out, cap.err


@pytest.fixture
def esptool(tmp_path: Path) -> str:
    p = tmp_path / "fake-esptool"
    p.write_text(FAKE_ESPTOOL)
    p.chmod(0o755)
    return str(p)


@pytest.fixture
def data(tmp_path, monkeypatch):
    d = tmp_path / "data"
    monkeypatch.setenv("XTEINK_DATA_DIR", str(d))
    return d


# --- backup -------------------------------------------------------------------------------


def test_backup_dry_run_prints_commands_runs_nothing(capsys, data):
    rc, out, _ = run(capsys, ["device", "backup", "--port", "/dev/ttyACM0"])
    assert rc == 0
    assert "uvx esptool@latest --port /dev/ttyACM0 --chip esp32c3 read-mac" in out
    assert "read-flash 0x0" in out and "dry-run" in out and str(data) in out
    assert not data.exists()
    rc, out, _ = run(capsys, ["device", "backup", "--port", "/dev/ttyACM0", "--json"])
    rep = json.loads(out)
    assert rep["applied"] is False and rep["commands"]["flash_id"][0] == "uvx"


def test_backup_apply_stores_dump_and_sha(capsys, data, esptool):
    rc, out, _ = run(
        capsys,
        ["device", "backup", "--port", "/dev/null", "--esptool", esptool, "--apply", "--json"],
    )
    rep = json.loads(out)
    assert rc == 0 and rep["mac"] == MAC and rep["bytes"] == SIZE
    dump = Path(rep["path"])
    assert dump.parent == data / "backups" / MAC.replace(":", "")
    assert dump.name.endswith("-full.bin") and dump.stat().st_size == SIZE
    digest = hashlib.sha256(dump.read_bytes()).hexdigest()
    assert rep["sha256"] == digest
    assert Path(rep["sha256_path"]).read_text().startswith(digest)
    assert [p.name for p in dump.parent.iterdir() if p.suffix not in (".bin", ".sha256")] == []


def test_backup_apply_esptool_failure_is_env_error(capsys, data, esptool):
    rc, _, err = run(
        capsys, ["device", "backup", "--port", "x", "--esptool", f"{esptool} --fail", "--apply"]
    )
    assert rc == 2 and "failed" in err


def test_backup_missing_esptool_is_env_error(capsys, data):
    rc, _, err = run(
        capsys, ["device", "backup", "--port", "x", "--esptool", "/nonexistent/esptool", "--apply"]
    )
    assert rc == 2 and "esptool" in err


def test_parsers():
    assert du.parse_mac("MAC: aa:bb:cc:dd:ee:ff") == MAC
    assert du.parse_flash_size("Detected flash size: 16MB") == 16 * 1024**2
    assert du.parse_flash_size("Detected flash size: 16 MB") == 16 * 1024**2


# --- provisioning fakes -------------------------------------------------------------------


class FakeTransport(du.Transport):
    """In-memory device: scripts replies per request, interleaves log lines."""

    def __init__(self, replies):
        self.replies = list(replies)  # callables (req_json) -> list[bytes lines]
        self.written = b""
        self.queue: list[bytes] = []
        self.requests: list[dict] = []
        self.closed = False
        self.max_chunk = 0

    def write(self, data):
        self.max_chunk = max(self.max_chunk, len(data))
        self.written += data
        if self.written.endswith(b"\n"):
            line, self.written = self.written.strip(), b""
            prefix, ver, payload = line.split(b" ")
            assert prefix == b"XTEINK-PROV" and ver == b"1" and len(line) <= 3072
            req = json.loads(base64.b64decode(payload))
            self.requests.append(req)
            self.queue += self.replies.pop(0)(req)

    def read_line(self, timeout):
        return self.queue.pop(0) if self.queue else None

    def discard_input(self):
        self.queue.clear()

    def close(self):
        self.closed = True


def ack(**kw):
    body = {"mac": MAC, "firmware_version": "1.2", "networks_saved": 1, "key_id": ""} | kw
    enc = base64.b64encode(json.dumps(body).encode())
    return [b"I [123] boot noise", b"XTEINK-PROV-ACK 1 " + enc, b"I trailing log"]


def err(code):
    return [b"E [1] something", f"XTEINK-PROV-ERR 1 {code}".encode()]


class FakeClient:
    def __init__(self):
        self.calls: list[tuple[str, str, object]] = []

    def _request(self, method, path, *, json_body=None, **kw):
        self.calls.append((method, path, json_body))
        if method == "POST" and path == "/api/devices":
            return {"device": {"id": 7, "name": json_body["name"]}, "key": KEY}
        return {}


@pytest.fixture
def nets(tmp_path):
    p = tmp_path / "networks.json"
    p.write_text(json.dumps([{"ssid": "home", "password": PASSWORD}]))
    p.chmod(0o600)
    return p


@pytest.fixture
def fakes(monkeypatch, data):
    client = FakeClient()
    monkeypatch.setattr(du, "make_client", lambda: client)
    monkeypatch.setattr(du, "CHUNK_GAP", 0)
    state = {"tp": None}

    def install(replies):
        state["tp"] = FakeTransport(replies)
        monkeypatch.setattr(du, "open_transport", lambda port: state["tp"])
        return state["tp"]

    install.client = client
    return install


def assert_no_secrets(*texts):
    for t in texts:
        assert KEY not in t and "SECRETSECRET" not in t and PASSWORD not in t


# --- provision ----------------------------------------------------------------------------


def test_provision_dry_run_no_io(capsys, fakes, nets):
    tp = fakes([])
    rc, out, err_ = run(
        capsys, ["device", "provision", "--port", "/dev/ttyACM0", "--networks-file", str(nets)]
    )
    assert rc == 0 and "dry-run" in out and "Provision via USB" in out and "masked" in out
    assert tp.requests == [] and fakes.client.calls == []
    assert_no_secrets(out, err_)
    rc, out, _ = run(
        capsys, ["device", "provision", "--port", "p", "--networks-file", str(nets), "--json"]
    )
    assert json.loads(out)["applied"] is False
    assert_no_secrets(out)


def test_provision_apply_happy_path(capsys, fakes, nets):
    tp = fakes([lambda r: ack(), lambda r: ack(networks_saved=1, key_id="0a1b2c3d")])
    rc, out, err_ = run(
        capsys,
        [
            "device",
            "provision",
            "--port",
            "/dev/ttyACM0",
            "--networks-file",
            str(nets),
            "--apply",
            "--json",
        ],
    )
    rep = json.loads(out)
    assert (
        rc == 0 and rep["key_id"] == "0a1b2c3d" and rep["mac"] == MAC and rep["networks_saved"] == 1
    )
    assert rep["name"] == "xteink-ddeeff"
    assert_no_secrets(out, err_)
    hello, msg = tp.requests
    assert hello == {}
    assert msg["device_key"] == KEY and msg["networks"] == [{"ssid": "home", "password": PASSWORD}]
    assert msg["lan_url"] == du.DEFAULT_LAN_URL and msg["tunnel_url"] == du.DEFAULT_TUNNEL_URL
    assert tp.max_chunk <= 128 and tp.closed
    assert [c[:2] for c in fakes.client.calls] == [("POST", "/api/devices")]


def test_provision_apply_text_hides_key(capsys, fakes, nets):
    fakes([lambda r: ack(), lambda r: ack(key_id="0a1b2c3d")])
    rc, out, err_ = run(
        capsys, ["device", "provision", "--port", "p", "--networks-file", str(nets), "--apply"]
    )
    assert rc == 0 and "0a1b2c3d" in out
    assert_no_secrets(out, err_)


def test_provision_not_in_mode_fails_before_minting(capsys, fakes, nets):
    fakes([lambda r: err("not_in_provisioning_mode")])
    rc, out, err_ = run(
        capsys, ["device", "provision", "--port", "p", "--networks-file", str(nets), "--apply"]
    )
    assert rc == 1 and "Provision via USB" in err_ and fakes.client.calls == []


def test_provision_error_after_mint_revokes(capsys, fakes, nets):
    fakes([lambda r: ack(), lambda r: err("invalid_field")])
    rc, out, err_ = run(
        capsys, ["device", "provision", "--port", "p", "--networks-file", str(nets), "--apply"]
    )
    assert rc == 1 and "invalid_field" in err_ and "revoked" in err_
    assert fakes.client.calls[-1][:2] == ("POST", "/api/devices/7/revoke")
    assert_no_secrets(out, err_)


def test_provision_key_id_mismatch_revokes(capsys, fakes, nets):
    fakes([lambda r: ack(), lambda r: ack(key_id="deadbeef")])
    rc, _, err_ = run(
        capsys, ["device", "provision", "--port", "p", "--networks-file", str(nets), "--apply"]
    )
    assert rc == 2 and "does not match" in err_
    assert fakes.client.calls[-1][1] == "/api/devices/7/revoke"


def test_provision_storage_error_retries(capsys, fakes, nets):
    tp = fakes([lambda r: ack(), lambda r: err("storage_error"), lambda r: ack(key_id="0a1b2c3d")])
    rc, *_ = run(
        capsys, ["device", "provision", "--port", "p", "--networks-file", str(nets), "--apply"]
    )
    assert rc == 0 and len(tp.requests) == 3 and len(fakes.client.calls) == 1


def test_provision_networks_file_must_be_private(capsys, fakes, nets):
    nets.chmod(0o644)
    rc, _, err_ = run(
        capsys, ["device", "provision", "--port", "p", "--networks-file", str(nets), "--apply"]
    )
    assert rc == 1 and "chmod 600" in err_ and fakes.client.calls == []


def test_provision_prompt_uses_getpass(capsys, fakes, monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))  # no default networks file
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    answers = iter(["cafe", ""])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    monkeypatch.setattr(du.getpass, "getpass", lambda prompt="": PASSWORD)
    tp = fakes([lambda r: ack(), lambda r: ack(key_id="0a1b2c3d")])
    rc, out, err_ = run(capsys, ["device", "provision", "--port", "p", "--apply"])
    assert rc == 0 and tp.requests[1]["networks"] == [{"ssid": "cafe", "password": PASSWORD}]
    assert_no_secrets(out, err_)


def test_provision_has_no_password_flag():
    with pytest.raises(SystemExit) as ei:
        main(["device", "provision", "--port", "p", "--password", "x"])
    assert ei.value.code == 1


def test_timeout_without_reply(monkeypatch):
    tp = FakeTransport([lambda r: []])
    monkeypatch.setattr(du, "CHUNK_GAP", 0)
    with pytest.raises(du.CliError) as ei:
        du.exchange(tp, {}, timeout=0.05)
    assert ei.value.code == 2


# --- real termios transport, on a pty (never a real device) ------------------------------


def test_serial_transport_on_pty():
    master, slave = os.openpty()
    path = os.ttyname(slave)
    tp = du.SerialTransport(path)
    try:
        threading.Timer(0.05, lambda: os.write(master, b"log line\r\nhello\n")).start()
        assert tp.read_line(2) == b"log line"
        assert tp.read_line(2) == b"hello"
        assert tp.read_line(0.05) is None
        tp.write(b"ping\n")
        assert b"ping" in os.read(master, 100)
        tp.discard_input()
    finally:
        tp.close()
        os.close(master)
        os.close(slave)


def test_serial_transport_open_failure_is_env_error():
    with pytest.raises(du.CliError) as ei:
        du.SerialTransport("/nonexistent/tty")
    assert ei.value.code == 2
