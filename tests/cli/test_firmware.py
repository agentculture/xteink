"""``xteink firmware`` and the OTA fields of ``device list`` (against the stub API)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from xteink.cli import main

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "fw" / "valid_x3.bin"
COMMON = ["--commit", "abc123", "--pr", "https://example.test/pr/1"]


def run(capsys, argv):
    rc = main(argv)
    cap = capsys.readouterr()
    return rc, cap.out, cap.err


def test_upload_dry_run_validates_but_stores_nothing(api, capsys):
    rc, out, _ = run(capsys, ["firmware", "upload", str(FIXTURE), *COMMON, "--json"])
    payload = json.loads(out)
    assert rc == 0
    assert payload["applied"] is False
    assert payload["image"]["version"] == "1.6.5-dev"
    assert "firmware" not in payload
    # the only request was the server-side dry-run validation
    assert api.requests == [("POST", "/api/firmware")]
    assert b'name="dry_run"\r\n\r\ntrue' in api.bodies[-1]


def test_upload_dry_run_text_hint(api, capsys):
    rc, out, _ = run(capsys, ["firmware", "upload", str(FIXTURE), *COMMON])
    assert rc == 0
    assert "would store" in out and "--apply" in out


def test_upload_apply_stores(api, capsys):
    rc, out, _ = run(capsys, ["firmware", "upload", str(FIXTURE), *COMMON, "--apply", "--json"])
    payload = json.loads(out)
    assert rc == 0
    assert payload["applied"] is True and payload["created"] is True
    assert payload["firmware"]["id"] == 1
    assert b'name="dry_run"\r\n\r\nfalse' in api.bodies[-1]
    assert b'name="fork_commit"\r\n\r\nabc123' in api.bodies[-1]


def test_upload_bad_image_exits_1_and_stores_nothing(api, capsys, tmp_path):
    bad = tmp_path / "bad.bin"
    bad.write_bytes(b"BADIMAGE" * 4)
    for extra in ([], ["--apply"]):
        rc, out, err = run(capsys, ["firmware", "upload", str(bad), *COMMON, *extra])
        assert rc == 1
        assert out == ""
        assert err.startswith("error:") and "bad_magic" in err and "hint:" in err
    # every attempt was refused by the server; nothing succeeded
    assert api.writes == [("POST", "/api/firmware")] * 2


def test_upload_missing_file_exits_1_without_requests(api, capsys, tmp_path):
    rc, _, err = run(capsys, ["firmware", "upload", str(tmp_path / "nope.bin"), *COMMON])
    assert rc == 1 and "not a file" in err
    assert api.requests == []


def test_upload_requires_commit_and_pr(api, capsys):
    with pytest.raises(SystemExit) as exc:
        main(["firmware", "upload", str(FIXTURE)])
    assert exc.value.code == 1
    assert "--commit" in capsys.readouterr().err


def test_upload_server_down_exits_2(monkeypatch, capsys):
    monkeypatch.setenv("XTEINK_URL", "http://127.0.0.1:1")
    monkeypatch.setenv("XTEINK_API_KEY", "k")
    rc, _, _ = run(capsys, ["firmware", "upload", str(FIXTURE), *COMMON])
    assert rc == 2


def test_list_text_and_json(api, capsys):
    rc, out, _ = run(capsys, ["firmware", "list"])
    assert rc == 0 and "1.6.5-dev" in out
    rc, out, _ = run(capsys, ["firmware", "list", "--json"])
    assert json.loads(out)["firmware"][0]["id"] == 1


def test_offer_requires_target(api, capsys):
    with pytest.raises(SystemExit) as exc:
        main(["firmware", "offer", "1"])
    assert exc.value.code == 1
    assert "--device" in capsys.readouterr().err


def test_offer_dry_run_asks_server_to_dry_run(api, capsys):
    rc, out, _ = run(capsys, ["firmware", "offer", "1", "--device", "Reader One", "--json"])
    payload = json.loads(out)
    assert rc == 0
    assert payload["applied"] is False and payload["offered"] == [1]
    assert json.loads(api.bodies[-1])["dry_run"] is True


def test_offer_apply_device_by_version(api, capsys):
    rc, out, _ = run(
        capsys, ["firmware", "offer", "1.6.5-dev", "--device", "1", "--apply", "--json"]
    )
    assert rc == 0
    assert json.loads(out)["applied"] is True
    assert json.loads(api.bodies[-1])["dry_run"] is False


def test_offer_all(api, capsys):
    rc, out, _ = run(capsys, ["firmware", "offer", "1", "--all", "--apply", "--json"])
    payload = json.loads(out)
    assert rc == 0 and payload["offered"] == [1, 2] and payload["all"] is True
    rc, out, _ = run(capsys, ["firmware", "offer", "1", "--all"])
    assert rc == 0 and "2 offered" in out and "--apply" in out


def test_offer_rolled_back_device_exits_1(api, capsys):
    rc, _, err = run(capsys, ["firmware", "offer", "1", "--device", "2", "--apply"])
    assert rc == 1 and "rolled back" in err


def test_offer_unknown_firmware_exits_1(api, capsys):
    rc, _, err = run(capsys, ["firmware", "offer", "99", "--all"])
    assert rc == 1 and "no firmware matches" in err


def test_device_list_json_has_ota_and_daily_run_fields(api, capsys):
    api.devices[0].update(
        firmware_version="1.6.4",
        offered_firmware_id=1,
        last_run_at="2026-10-11T03:00:00+00:00",
        last_run_trigger="daily",
        last_fw_outcome="updated",
        last_content_outcome="ok",
    )
    rc, out, _ = run(capsys, ["device", "list", "--json"])
    d1, d2 = json.loads(out)["devices"]
    assert rc == 0
    assert d1["offered_firmware"] == {"id": 1, "version": "1.6.5-dev"}
    assert d1["firmware_version"] == "1.6.4"
    assert d1["last_run_at"] == "2026-10-11T03:00:00+00:00"
    assert d1["last_fw_outcome"] == "updated" and d1["last_content_outcome"] == "ok"
    assert d1["last_run_trigger"] == "daily"
    for k in (
        "offered_firmware",
        "firmware_version",
        "last_run_at",
        "last_run_trigger",
        "last_fw_outcome",
        "last_content_outcome",
    ):
        assert k in d2 and d2[k] is None
    rc, out, _ = run(capsys, ["device", "list"])
    assert "offered: 1.6.5-dev" in out and "fw: 1.6.4" in out
