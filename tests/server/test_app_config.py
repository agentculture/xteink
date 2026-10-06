"""Config / bootstrap tests that need no third-party packages."""

from pathlib import Path

import pytest

from xteink.core import KeyService, Store
from xteink.server import (
    DEFAULT_BIND,
    DEFAULT_DEVICE_PORT,
    DEFAULT_PORT,
    ServerConfig,
    load_config,
)
from xteink.server.__main__ import main as server_main

PKG = Path(__file__).resolve().parents[2] / "xteink"


def test_defaults():
    cfg = load_config({})
    assert cfg == ServerConfig(bind="0.0.0.0", port=8780, device_port=8781)
    assert (DEFAULT_BIND, DEFAULT_PORT, DEFAULT_DEVICE_PORT) == ("0.0.0.0", 8780, 8781)


def test_env_overrides():
    cfg = load_config(
        {"XTEINK_BIND": "127.0.0.1", "XTEINK_PORT": "9000", "XTEINK_DEVICE_PORT": "9001"}
    )
    assert cfg == ServerConfig(bind="127.0.0.1", port=9000, device_port=9001)


def test_blank_env_falls_back_to_defaults():
    assert load_config({"XTEINK_BIND": " ", "XTEINK_PORT": ""}) == load_config({})


@pytest.mark.parametrize("bad", ["abc", "0", "70000", "-1"])
def test_bad_port_rejected(bad):
    with pytest.raises(ValueError, match="XTEINK_PORT"):
        load_config({"XTEINK_PORT": bad})


def test_ports_must_differ():
    with pytest.raises(ValueError, match="differ"):
        load_config({"XTEINK_PORT": "9000", "XTEINK_DEVICE_PORT": "9000"})


def test_reads_os_environ(monkeypatch):
    monkeypatch.setenv("XTEINK_BIND", "100.64.0.1")
    assert load_config().bind == "100.64.0.1"


def test_no_cloudflare_token_reads_in_package():
    needle = "CLOUDFLARE" + "_API_" + "TOKEN"
    offenders = [
        str(p) for p in PKG.rglob("*") if p.is_file() and needle.encode() in p.read_bytes()
    ]
    assert offenders == []


def test_create_key_bootstrap(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("XTEINK_DATA_DIR", str(tmp_path / "data"))
    assert server_main(["create-key", "admin"]) == 0
    raw = capsys.readouterr().out.strip()
    assert raw.startswith("xtk_")
    key = KeyService(Store(tmp_path / "data")).authenticate(raw)
    assert key.name == "admin"


def test_create_key_requires_name(capsys):
    with pytest.raises(SystemExit) as exc:
        server_main(["create-key"])
    assert exc.value.code != 0


def test_serve_bad_env_is_env_error(monkeypatch, capsys):
    monkeypatch.setenv("XTEINK_PORT", "nope")
    assert server_main(["serve"]) == 2
    assert "XTEINK_PORT" in capsys.readouterr().err
