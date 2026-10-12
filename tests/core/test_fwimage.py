"""ESP image header validator: synthetic fixtures only, never a real firmware blob."""

import ast
import struct
from pathlib import Path

import pytest

from xteink.core import fwimage
from xteink.core.fwimage import FirmwareImageError, ImageInfo, validate

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "fw"
MODULE = Path(fwimage.__file__)


def make_image(chip=0x0005, tag=b"CROSSPOINT-BOARD-V1:x4;", version=b"1.6.5-dev", magic=0xE9):
    header = bytes([magic]) + bytes(11) + struct.pack("<H", chip) + bytes(10)
    body = b"\x00" * 16
    if tag:
        body += tag + b"\x00" * 4
    if version:
        body += b"CrossPoint version: " + version + b"\x00"
    return header + body


@pytest.mark.parametrize("name", ["valid_x3.bin"])
def test_committed_fixture_accepted(name):
    path = FIXTURES / name
    assert path.stat().st_size < 1024
    info = validate(path)
    assert isinstance(info, ImageInfo)
    assert info.chip_id == 0x0005
    assert info.board == "x4"
    assert info.version == "1.6.5-dev"


def test_valid_in_tmp(tmp_path):
    p = tmp_path / "a.bin"
    p.write_bytes(make_image())
    info = validate(p)
    assert (info.chip_id, info.board, info.version) == (0x0005, "x4", "1.6.5-dev")
    assert info.size == p.stat().st_size


def test_no_version_is_none(tmp_path):
    p = tmp_path / "a.bin"
    p.write_bytes(make_image(version=b""))
    assert validate(p).version is None


def test_untagged_image_passes_like_firmware(tmp_path):
    p = tmp_path / "a.bin"
    p.write_bytes(make_image(tag=b""))
    assert validate(p).board is None


def _msg(path):
    with pytest.raises(FirmwareImageError) as exc:
        validate(path)
    return str(exc.value), exc.value.code


def test_rejections_have_distinct_messages(tmp_path):
    cases = {}
    p = tmp_path / "notesp.bin"
    p.write_bytes(b"PK\x03\x04" + bytes(40))
    cases["magic"] = _msg(p)
    p = tmp_path / "s3.bin"
    p.write_bytes(make_image(chip=0x0009))
    cases["chip"] = _msg(p)
    p = tmp_path / "board.bin"
    p.write_bytes(make_image(tag=b"CROSSPOINT-BOARD-V1:sticky;"))
    cases["board"] = _msg(p)
    p = tmp_path / "big.bin"
    p.write_bytes(make_image())
    with open(p, "r+b") as fh:
        fh.truncate(0x640000 + 1)
    cases["size"] = _msg(p)
    p = tmp_path / "short.bin"
    p.write_bytes(b"\xe9\x00")
    cases["short"] = _msg(p)
    messages = [m for m, _ in cases.values()]
    codes = [c for _, c in cases.values()]
    assert len(set(messages)) == len(messages)
    assert len(set(codes)) == len(codes)


def test_exactly_max_size_accepted(tmp_path):
    p = tmp_path / "max.bin"
    p.write_bytes(make_image())
    with open(p, "r+b") as fh:
        fh.truncate(0x640000)
    assert validate(p).size == 0x640000


def test_missing_file(tmp_path):
    with pytest.raises(FirmwareImageError):
        validate(tmp_path / "nope.bin")


def test_stdlib_only_imports():
    import sys

    tree = ast.parse(MODULE.read_text())
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "relative import of another xteink module"
            names = [node.module]
        for n in names:
            top = n.split(".")[0]
            assert top in sys.stdlib_module_names, n
