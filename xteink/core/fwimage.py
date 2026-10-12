"""ESP firmware image header validator for the X3 (pure, stdlib only).

Mirrors the device-side OTA guard in the firmware fork
(``xteink-firmware`` branch ``feat/issue-1``) so the server rejects an image the
device would refuse anyway:

* chip id: ``src/network/OtaUpdater.cpp:184-186`` buffers the first 14 bytes and
  reads a little-endian ``uint16`` at ``esp_image_header_t`` offset 12
  (``OtaUpdater.cpp:196-198``); a mismatch with the running chip aborts
  (``OtaUpdater.cpp:200-205``). Here the expected chip is ESP32-C3 (0x0005).
* board tag: ``OtaUpdater.cpp:187-194`` / ``:207-214`` scan the whole image with
  ``board_tag::Scanner`` (``src/network/FirmwareBoardTag.cpp:53-83``) for
  ``CROSSPOINT-BOARD-V1:<board>;`` (``FirmwareBoardTag.cpp:48``). The X3 and X4
  share one ESP32-C3 binary tagged ``x4`` (``FirmwareBoardTag.cpp:16-17``). As in
  the firmware, an untagged image passes (``board`` is ``None``); a tag naming
  any other board, or any occurrence that differs, is rejected.
* version: ``CROSSPOINT_VERSION`` is a compile-time string literal with no marker
  of its own; the firmware concatenates it into ``"CrossPoint version: "``
  (``lib/hal/HalSystem.cpp:168``), which is what is searched for here.

The ESP image magic byte (0xE9) is checked first, and the image may be at most
0x640000 bytes (OTA slot size).
"""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass
from pathlib import Path

ESP_IMAGE_MAGIC = 0xE9
CHIP_ID_OFFSET = 12
CHIP_ID_ESP32_C3 = 0x0005
CHIP_ID_ESP32_S3 = 0x0009
EXPECTED_BOARD = "x4"
MAX_IMAGE_SIZE = 0x640000
HEADER_LEN = CHIP_ID_OFFSET + 2

_TAG_RE = re.compile(rb"CROSSPOINT-BOARD-V1:([\x21-\x3a\x3c-\x7e]{0,23});")
_VERSION_RE = re.compile(rb"CrossPoint version: ([\x21-\x7e]{1,64})")


class FirmwareImageError(ValueError):
    """The image failed validation; ``code`` is a stable machine-readable reason."""

    def __init__(self, message: str, code: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ImageInfo:
    path: Path
    size: int
    chip_id: int
    board: str | None
    version: str | None


def validate(path: str | Path) -> ImageInfo:
    """Validate an X3 firmware image or raise :class:`FirmwareImageError`."""
    p = Path(path)
    try:
        size = p.stat().st_size
    except OSError as exc:
        raise FirmwareImageError(
            f"cannot read firmware image: {exc.strerror}", "unreadable"
        ) from exc
    if size > MAX_IMAGE_SIZE:
        raise FirmwareImageError(
            f"image is {size} bytes, larger than the OTA limit of {MAX_IMAGE_SIZE:#x}",
            "too_large",
        )
    try:
        data = p.read_bytes()
    except OSError as exc:
        raise FirmwareImageError(
            f"cannot read firmware image: {exc.strerror}", "unreadable"
        ) from exc
    if len(data) < HEADER_LEN:
        raise FirmwareImageError("file too short to hold an ESP image header", "truncated")
    if data[0] != ESP_IMAGE_MAGIC:
        raise FirmwareImageError("not an ESP image: bad magic byte (expected 0xE9)", "bad_magic")
    (chip_id,) = struct.unpack_from("<H", data, CHIP_ID_OFFSET)
    if chip_id != CHIP_ID_ESP32_C3:
        raise FirmwareImageError(
            f"wrong chip: image={chip_id:#06x}, expected ESP32-C3 ({CHIP_ID_ESP32_C3:#06x})",
            "wrong_chip",
        )
    board = None
    for match in _TAG_RE.finditer(data):
        name = match.group(1).decode("ascii")
        if name != EXPECTED_BOARD:
            raise FirmwareImageError(
                f"wrong board tag: image={name!r}, expected {EXPECTED_BOARD!r} (X3)",
                "wrong_board",
            )
        board = name
    vm = _VERSION_RE.search(data)
    version = vm.group(1).decode("ascii") if vm else None
    return ImageInfo(path=p, size=size, chip_id=chip_id, board=board, version=version)
