"""``xteink device backup`` / ``device provision`` — talk to a plugged-in reader over USB.

* ``backup`` shells out to ``esptool`` (an external tool, never a dependency; default
  ``uvx esptool@latest``, override with ``--esptool``) to dump the whole flash and stores the
  dump plus its sha256 under ``<data dir>/backups/<MAC>/``.
* ``provision`` mints a device key through the API and sends Wi-Fi networks, server URLs and
  the key over the USB serial port using the fork's ``XTEINK-PROV 1`` wire format
  (``xteink-firmware/docs/provisioning.md``).

Both verbs are dry-run unless ``--apply`` is given. The device key and Wi-Fi passwords are never
accepted on argv and never printed or logged (stdout, stderr, ``--json``).

Serial I/O is stdlib-only (``os`` + ``termios`` + ``select``) behind the tiny :class:`Transport`
interface so tests can inject an in-memory fake. This module does not import ``xteink.core``.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import getpass
import hashlib
import json
import os
import re
import select
import shlex
import stat
import subprocess  # nosec B404 - argv list, shell=False, external esptool by design
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from xteink.cli._commands.server import add_json, call, json_mode, make_client
from xteink.cli._errors import EXIT_ENV_ERROR, EXIT_USER_ERROR, CliError
from xteink.cli._output import emit_diagnostic, emit_result

DRY_RUN_HINT = "dry-run: nothing was touched; re-run with --apply to do it."
DEFAULT_ESPTOOL = "uvx esptool@latest"
DEFAULT_CHIP = "esp32c3"
DEFAULT_LAN_URL = "http://xteink.local:8781"
DEFAULT_TUNNEL_URL = "https://xteink.culture.dev"
DEFAULT_NETWORKS_FILE = "~/.config/xteink/networks.json"
PROV_INSTRUCTION = (
    "On the device open Settings > System > Provision via USB "
    '(it shows "Waiting for computer...") before running this with --apply.'
)

PROTOCOL_VERSION = 1
MAX_LINE = 3072
MAX_JSON = 2048
CHUNK = 128
CHUNK_GAP = 0.01
REPLY_TIMEOUT = 5.0
MAX_NETWORKS = 8
STORAGE_RETRIES = 2

# Data dir resolution is reimplemented here on purpose (the CLI must not import xteink.core);
# it mirrors xteink.core.store.
DATA_DIR_ENV = "XTEINK_DATA_DIR"
DEFAULT_DATA_DIR = "~/.local/share/xteink"

_MAC_RE = re.compile(r"MAC:\s*((?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2})")
_FLASH_RE = re.compile(r"Detected flash size:\s*(\d+)\s*([KMG]?)B", re.IGNORECASE)
_KEY_RE = re.compile(r"^xtd_([0-9a-f]{8})_[A-Za-z0-9_-]+$")


def data_dir() -> Path:
    return Path(os.environ.get(DATA_DIR_ENV) or DEFAULT_DATA_DIR).expanduser()


# --- esptool shell-out (mirrors reterminal-cli firmware.py) ------------------------------


def _esptool_base(args: argparse.Namespace) -> list[str]:
    return shlex.split(args.esptool) + ["--port", args.port, "--chip", args.chip]


def _run(argv: list[str], *, timeout: float, what: str) -> str:
    try:
        cp = subprocess.run(  # nosec B603 - argv list, shell=False
            argv, capture_output=True, text=True, timeout=timeout, check=False
        )
    except FileNotFoundError:
        raise CliError(
            EXIT_ENV_ERROR,
            f"cannot run {argv[0]!r}",
            "install uv (for 'uvx esptool@latest') or pass --esptool PATH",
        ) from None
    except subprocess.TimeoutExpired:
        raise CliError(EXIT_ENV_ERROR, f"{what} timed out after {timeout:.0f}s") from None
    if cp.returncode != 0:
        tail = (cp.stderr or cp.stdout or "").strip().splitlines()
        raise CliError(
            EXIT_ENV_ERROR,
            f"{what} failed: {tail[-1] if tail else f'exit {cp.returncode}'}",
            "is the device connected on --port, awake, and the port free?",
        )
    return (cp.stdout or "") + (cp.stderr or "")


def parse_mac(text: str) -> str:
    m = _MAC_RE.search(text)
    if not m:
        raise CliError(EXIT_ENV_ERROR, "could not read the MAC from esptool output")
    return m.group(1).upper()


def parse_flash_size(text: str) -> int:
    m = _FLASH_RE.search(text)
    if not m:
        raise CliError(EXIT_ENV_ERROR, "could not read the flash size from esptool output")
    mult = {"": 1, "K": 1024, "M": 1024**2, "G": 1024**3}[m.group(2).upper()]
    return int(m.group(1)) * mult


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def cmd_backup(args: argparse.Namespace) -> int:
    base = _esptool_base(args)
    steps = {
        "read_mac": base + ["read-mac"],
        "flash_id": base + ["flash-id"],
        "read_flash": base + ["read-flash", "0x0", "<flash-size-bytes>", "<dump.bin>"],
    }
    target = data_dir() / "backups" / "<MAC>" / "<UTC timestamp>-full.bin"
    if not args.apply:
        payload = {
            "action": "backup",
            "applied": False,
            "port": args.port,
            "commands": steps,
            "target": str(target),
        }
        text = "would run:\n" + "\n".join(
            f"  {name}: {shlex.join(argv)}" for name, argv in steps.items()
        )
        text += f"\nand store the dump + .sha256 at {target}\n{DRY_RUN_HINT}"
        emit_result(payload if json_mode(args) else text, json_mode=json_mode(args))
        return 0

    mac = parse_mac(_run(steps["read_mac"], timeout=args.timeout, what="reading MAC"))
    size = parse_flash_size(_run(steps["flash_id"], timeout=args.timeout, what="reading flash id"))
    out_dir = data_dir() / "backups" / mac.replace(":", "")
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    final = out_dir / f"{stamp}-full.bin"
    with tempfile.TemporaryDirectory(dir=out_dir) as tmp:
        part = Path(tmp) / "dump.bin"
        emit_diagnostic(f"reading {size} bytes of flash from {args.port} (this takes minutes)")
        _run(
            base + ["read-flash", "0x0", hex(size), str(part)],
            timeout=args.timeout,
            what="reading flash",
        )
        got = part.stat().st_size if part.exists() else 0
        if got != size:
            raise CliError(EXIT_ENV_ERROR, f"dump is {got} bytes, expected {size}")
        digest = _sha256_file(part)
        os.replace(part, final)
    sha_path = final.with_name(final.name + ".sha256")
    sha_path.write_text(f"{digest}  {final.name}\n", encoding="utf-8")
    payload = {
        "action": "backup",
        "applied": True,
        "port": args.port,
        "mac": mac,
        "bytes": size,
        "path": str(final),
        "sha256": digest,
        "sha256_path": str(sha_path),
    }
    text = f"backup: {final}\nsha256: {digest}\nmac: {mac}  bytes: {size}"
    emit_result(payload if json_mode(args) else text, json_mode=json_mode(args))
    return 0


# --- serial transport (stdlib only) -----------------------------------------------------


class Transport:
    """Minimal byte-stream interface the provisioning client needs."""

    def write(self, data: bytes) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def read_line(self, timeout: float) -> bytes | None:  # pragma: no cover - interface
        """Return one line (without newline) or ``None`` on timeout."""
        raise NotImplementedError

    def discard_input(self) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def close(self) -> None:  # pragma: no cover - interface
        raise NotImplementedError


class SerialTransport(Transport):
    """Raw-mode tty via ``os.open`` + ``termios``; never toggles DTR/RTS on purpose."""

    def __init__(self, path: str) -> None:
        import termios  # POSIX only; imported lazily so the module imports everywhere

        self._termios = termios
        try:
            self._fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        except OSError as exc:
            raise CliError(
                EXIT_ENV_ERROR,
                f"cannot open {path}: {exc.strerror}",
                "is the device plugged in and awake (it sleeps; press a button)?",
            ) from None
        try:
            attrs = termios.tcgetattr(self._fd)
            attrs[0] = 0  # iflag
            attrs[1] = 0  # oflag
            attrs[2] = (attrs[2] & ~(termios.CSIZE | termios.PARENB | termios.HUPCL)) | (
                termios.CS8 | termios.CLOCAL | termios.CREAD
            )
            attrs[3] = 0  # lflag: raw
            attrs[4] = attrs[5] = termios.B115200
            attrs[6][termios.VMIN] = 0
            attrs[6][termios.VTIME] = 0
            termios.tcsetattr(self._fd, termios.TCSANOW, attrs)
        except Exception as exc:  # termios.error and friends
            os.close(self._fd)
            raise CliError(EXIT_ENV_ERROR, f"cannot configure {path}: {exc}") from None
        self._buf = b""

    def write(self, data: bytes) -> None:
        view = memoryview(data)
        deadline = time.monotonic() + 5.0
        while view:
            _, w, _ = select.select([], [self._fd], [], 0.5)
            if w:
                n = os.write(self._fd, view)
                view = view[n:]
            elif time.monotonic() > deadline:
                raise CliError(EXIT_ENV_ERROR, "timed out writing to the serial port")

    def read_line(self, timeout: float) -> bytes | None:
        deadline = time.monotonic() + timeout
        while True:
            if b"\n" in self._buf:
                line, self._buf = self._buf.split(b"\n", 1)
                return line.rstrip(b"\r")
            left = deadline - time.monotonic()
            if left <= 0:
                return None
            r, _, _ = select.select([self._fd], [], [], left)
            if r:
                try:
                    chunk = os.read(self._fd, 4096)
                except BlockingIOError:
                    continue
                except OSError as exc:
                    raise CliError(EXIT_ENV_ERROR, f"serial read failed: {exc.strerror}") from None
                self._buf += chunk

    def discard_input(self) -> None:
        self._buf = b""
        self._termios.tcflush(self._fd, self._termios.TCIFLUSH)

    def close(self) -> None:
        try:
            os.close(self._fd)
        except OSError:
            pass


def open_transport(port: str) -> Transport:
    """Open the serial port. Tests monkeypatch this to inject a fake."""
    return SerialTransport(port)


# --- provisioning protocol --------------------------------------------------------------


def _b64_json(obj: dict[str, Any]) -> str:
    raw = json.dumps(obj, separators=(",", ":")).encode()
    if len(raw) > MAX_JSON:
        raise CliError(
            EXIT_USER_ERROR,
            f"provisioning JSON is {len(raw)} bytes (max {MAX_JSON})",
            "use fewer or shorter networks",
        )
    return base64.b64encode(raw).decode()


def exchange(tp: Transport, obj: dict[str, Any], timeout: float = REPLY_TIMEOUT) -> dict[str, Any]:
    """Send one request, return the ACK JSON; raise :class:`CliError` on ERR/timeout."""
    # The leading newline ends any stray partial line already in the device RX
    # buffer (the firmware ignores empty lines); seen once as bad_format on the X3.
    line = f"\nXTEINK-PROV {PROTOCOL_VERSION} {_b64_json(obj)}\n".encode()
    if len(line) > MAX_LINE:
        raise CliError(EXIT_USER_ERROR, f"request line is {len(line)} bytes (max {MAX_LINE})")
    tp.discard_input()
    for i in range(0, len(line), CHUNK):
        tp.write(line[i : i + CHUNK])
        time.sleep(CHUNK_GAP)
    deadline = time.monotonic() + timeout
    while True:
        left = deadline - time.monotonic()
        if left <= 0:
            raise CliError(
                EXIT_ENV_ERROR,
                "no reply from the device",
                "is Settings > System > Provision via USB open, on a non-slim firmware build?",
            )
        raw = tp.read_line(left)
        if raw is None:
            continue
        text = raw.decode("utf-8", errors="replace").strip()
        if text.startswith("XTEINK-PROV-ACK"):
            parts = text.split(" ", 2)
            try:
                return json.loads(base64.b64decode(parts[2], validate=True))
            except (IndexError, ValueError):
                raise CliError(EXIT_ENV_ERROR, "device sent an unreadable ACK") from None
        if text.startswith("XTEINK-PROV-ERR"):
            code = text.split(" ", 2)[-1].strip()
            raise ProvError(code)
        # anything else is interleaved firmware log output: ignore


class ProvError(CliError):
    """A device-side ``XTEINK-PROV-ERR`` reply."""

    def __init__(self, code: str) -> None:
        self.device_code = code
        if code == "not_in_provisioning_mode":
            super().__init__(EXIT_USER_ERROR, f"device refused: {code}", PROV_INSTRUCTION)
        elif code == "storage_error":
            super().__init__(EXIT_ENV_ERROR, f"device refused: {code}", "retry the command")
        else:
            super().__init__(EXIT_USER_ERROR, f"device refused: {code}")


def exchange_retry(tp: Transport, obj: dict[str, Any]) -> dict[str, Any]:
    for attempt in range(STORAGE_RETRIES + 1):
        try:
            return exchange(tp, obj)
        except ProvError as exc:
            if exc.device_code != "storage_error" or attempt == STORAGE_RETRIES:
                raise
    raise AssertionError("unreachable")  # pragma: no cover


# --- networks ---------------------------------------------------------------------------


def _validate_networks(nets: Any, source: str) -> list[dict[str, str]]:
    if not isinstance(nets, list):
        raise CliError(EXIT_USER_ERROR, f"{source}: expected a JSON list of {{ssid, password}}")
    out: list[dict[str, str]] = []
    for n in nets:
        if not isinstance(n, dict) or not isinstance(n.get("ssid"), str) or not n["ssid"]:
            raise CliError(EXIT_USER_ERROR, f"{source}: every entry needs a non-empty 'ssid'")
        pw = n.get("password", "")
        if not isinstance(pw, str) or len(pw.encode()) > 64 or len(n["ssid"].encode()) > 32:
            raise CliError(EXIT_USER_ERROR, f"{source}: ssid max 32 bytes, password max 64 bytes")
        out.append({"ssid": n["ssid"], "password": pw})
    if len({n["ssid"] for n in out}) != len(out):
        raise CliError(EXIT_USER_ERROR, f"{source}: duplicate ssid")
    if len(out) > MAX_NETWORKS:
        raise CliError(EXIT_USER_ERROR, f"{source}: at most {MAX_NETWORKS} networks")
    return out


def load_networks_file(path: Path) -> list[dict[str, str]]:
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise CliError(
            EXIT_USER_ERROR,
            f"{path} is readable by others (mode {mode:o})",
            f"chmod 600 {path}",
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CliError(EXIT_USER_ERROR, f"cannot read {path}: {exc.__class__.__name__}") from None
    return _validate_networks(data, str(path))


def prompt_networks() -> list[dict[str, str]]:
    if not sys.stdin.isatty():
        raise CliError(
            EXIT_USER_ERROR,
            "no networks given",
            f"create {DEFAULT_NETWORKS_FILE} (chmod 600), pass --networks-file, or run on a "
            "terminal to be prompted, or pass --no-networks",
        )
    nets: list[dict[str, str]] = []
    while len(nets) < MAX_NETWORKS:
        ssid = input("Wi-Fi SSID (blank to finish): ").strip()
        if not ssid:
            break
        nets.append({"ssid": ssid, "password": getpass.getpass(f"password for {ssid!r}: ")})
    return _validate_networks(nets, "prompt")


def _networks_source(args: argparse.Namespace) -> Path | None:
    if args.no_networks:
        return None
    if args.networks_file:
        p = Path(args.networks_file).expanduser()
        if not p.is_file():
            raise CliError(EXIT_USER_ERROR, f"networks file not found: {p}")
        return p
    p = Path(DEFAULT_NETWORKS_FILE).expanduser()
    return p if p.is_file() else None


# --- provision --------------------------------------------------------------------------


def _key_id(key: Any) -> str:
    m = _KEY_RE.match(key) if isinstance(key, str) else None
    if not m:
        raise CliError(EXIT_ENV_ERROR, "server returned a device key in an unexpected format")
    return m.group(1)


def cmd_provision(args: argparse.Namespace) -> int:
    src = _networks_source(args)
    if not args.apply:
        payload = {
            "action": "provision",
            "applied": False,
            "port": args.port,
            "name": args.name or "xteink-<mac suffix>",
            "networks": (
                "none"
                if args.no_networks
                else f"from {src}" if src else "prompted at --apply (passwords hidden)"
            ),
            "lan_url": args.lan_url,
            "tunnel_url": args.tunnel_url,
            "device_key": "<minted via API at --apply; never printed>",
            "replace_networks": bool(args.replace_networks),
        }
        text = "\n".join(
            [
                "would mint a device key via the API, then send over USB:",
                f"  port: {args.port}",
                f"  device name: {payload['name']}",
                f"  networks: {payload['networks']} (passwords masked)",
                f"  lan_url: {args.lan_url}",
                f"  tunnel_url: {args.tunnel_url}",
                "  device_key: <masked>",
                PROV_INSTRUCTION,
                DRY_RUN_HINT,
            ]
        )
        emit_result(payload if json_mode(args) else text, json_mode=json_mode(args))
        return 0

    if args.no_networks:
        networks: list[dict[str, str]] = []
    elif src:
        networks = load_networks_file(src)
    else:
        networks = prompt_networks()

    client = make_client()
    tp = open_transport(args.port)
    minted: dict[str, Any] | None = None
    try:
        emit_diagnostic(PROV_INSTRUCTION)
        hello = exchange_retry(tp, {})
        mac = str(hello.get("mac", ""))
        name = args.name or f"xteink-{mac.replace(':', '').lower()[-6:] or 'device'}"
        minted = call(lambda: client.register_device(name, mirror=False))
        key = minted["key"]
        expect_id = _key_id(key)
        msg: dict[str, Any] = {
            "networks": networks,
            "replace_networks": bool(args.replace_networks),
            "lan_url": args.lan_url,
            "tunnel_url": args.tunnel_url,
            "device_key": key,
        }
        ack = exchange_retry(tp, msg)
        if ack.get("key_id") != expect_id:
            raise CliError(EXIT_ENV_ERROR, "device ACK key id does not match the minted key")
    except BaseException as exc:
        revoked = False
        if minted is not None:
            try:
                dev_id = int(minted["device"]["id"])
                client.revoke_device(dev_id)
                revoked = True
            except Exception:  # best effort; reported below
                revoked = False
            note = (
                "the freshly minted key was revoked"
                if revoked
                else "COULD NOT revoke the minted key: run 'xteink device revoke' for it"
            )
            if isinstance(exc, CliError):
                raise CliError(
                    exc.code, exc.message, f"{note}; {exc.remediation}" if exc.remediation else note
                ) from None
            emit_diagnostic(note)
        raise
    finally:
        tp.close()

    payload = {
        "action": "provision",
        "applied": True,
        "port": args.port,
        "mac": ack.get("mac", mac),
        "firmware_version": ack.get("firmware_version", ""),
        "device_id": minted["device"]["id"],
        "name": name,
        "key_id": expect_id,
        "networks_saved": ack.get("networks_saved"),
    }
    text = (
        f"provisioned {payload['mac']} as {name!r}\n"
        f"key id: {expect_id}\nnetworks saved: {payload['networks_saved']}\n"
        "Press Back on the device to leave the provisioning screen."
    )
    emit_result(payload if json_mode(args) else text, json_mode=json_mode(args))
    return 0


# --- registration -----------------------------------------------------------------------


def _add_port(p: argparse.ArgumentParser) -> None:
    p.add_argument("--port", required=True, metavar="PORT", help="Serial port, e.g. /dev/ttyACM0.")


def register_usb(nsub: argparse._SubParsersAction) -> None:
    """Add ``backup`` and ``provision`` under the existing ``device`` noun."""
    b = nsub.add_parser(
        "backup", help="Dump the device flash over USB with esptool (dry-run by default)."
    )
    _add_port(b)
    b.add_argument(
        "--esptool",
        default=DEFAULT_ESPTOOL,
        help=f"esptool command (default: {DEFAULT_ESPTOOL!r}).",
    )
    b.add_argument("--chip", default=DEFAULT_CHIP, help=f"Chip (default {DEFAULT_CHIP}).")
    b.add_argument("--timeout", type=float, default=900.0, help="Per-step timeout, seconds.")
    b.add_argument("--apply", action="store_true", help="Actually read the flash.")
    add_json(b)
    b.set_defaults(func=cmd_backup)

    p = nsub.add_parser(
        "provision",
        help="Mint a device key and send Wi-Fi/URLs/key over USB (dry-run by default).",
    )
    _add_port(p)
    p.add_argument("--name", help="Device name (default derived from the MAC).")
    p.add_argument(
        "--networks-file",
        metavar="PATH",
        help=f"JSON list of {{ssid, password}} (default {DEFAULT_NETWORKS_FILE}, chmod 600, "
        "never commit it); without a file you are prompted. Passwords are never argv flags.",
    )
    p.add_argument("--no-networks", action="store_true", help="Send no Wi-Fi networks.")
    p.add_argument("--replace-networks", action="store_true", help="Replace saved networks.")
    p.add_argument("--lan-url", default=DEFAULT_LAN_URL, help="LAN server URL.")
    p.add_argument("--tunnel-url", default=DEFAULT_TUNNEL_URL, help="Tunnel (https) server URL.")
    p.add_argument("--apply", action="store_true", help="Actually mint the key and provision.")
    add_json(p)
    p.set_defaults(func=cmd_provision)
