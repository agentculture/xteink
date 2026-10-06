"""Upload containment and Markdown/HTML to EPUB conversion.

Every upload path (web, API, MCP) must go through :func:`ingest`. Guards, in order:
size cap, magic/format check, EPUB zip-bomb caps, then (for Markdown/HTML) a
timeout-bounded ``pandoc`` subprocess with ``shell=False`` and no network access.
"""

from __future__ import annotations

import io
import os
import shutil
import subprocess  # nosec B404 - shell=False, fixed argv (pandoc)
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .errors import CoreError
from .library import LibraryService
from .models import AddResult

EPUB_MIMETYPE = b"application/epub+zip"
BMP_MAGIC = b"BM"
PDF_MAGIC = b"%PDF"
MARKUP_EXTENSIONS = {".md", ".markdown", ".html", ".htm"}
_PANDOC_FROM = {".md": "markdown", ".markdown": "markdown", ".html": "html", ".htm": "html"}


class IngestError(CoreError):
    """An upload was refused or could not be converted. ``code`` is machine-readable."""

    code = "ingest_error"

    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        if code is not None:
            self.code = code


class IngestEnvironmentError(IngestError):
    """The host lacks something needed (e.g. pandoc). Map to 5xx / CLI exit code 2."""

    code = "converter_missing"


@dataclass(frozen=True)
class IngestLimits:
    max_bytes: int = 50 * 1024 * 1024
    max_zip_entries: int = 5000
    max_uncompressed_bytes: int = 500 * 1024 * 1024
    convert_timeout_s: float = 60.0


DEFAULT_LIMITS = IngestLimits()


@dataclass(frozen=True)
class PreparedUpload:
    data: bytes
    format: str
    kind: str
    title: str
    author: str


def _check_epub(data: bytes, limits: IngestLimits) -> bool:
    """Return True if data is a safe EPUB; False if not a zip/EPUB; raise on bomb."""
    if not data.startswith(b"PK"):
        return False
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        return False
    with zf:
        infos = zf.infolist()
        if len(infos) > limits.max_zip_entries:
            raise IngestError("EPUB has too many entries", "zip_bomb")
        if sum(i.file_size for i in infos) > limits.max_uncompressed_bytes:
            raise IngestError("EPUB uncompressed size is too large", "zip_bomb")
        if not infos or infos[0].filename != "mimetype":
            return False
        if infos[0].file_size > len(EPUB_MIMETYPE):
            return False
        return zf.read("mimetype") == EPUB_MIMETYPE


def _is_text(data: bytes) -> bool:
    if b"\x00" in data:
        return False
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def _convert(data: bytes, ext: str, title: str, author: str, limits: IngestLimits) -> bytes:
    pandoc = shutil.which("pandoc")
    if pandoc is None:
        raise IngestEnvironmentError("pandoc is not installed; cannot convert to EPUB")
    with tempfile.TemporaryDirectory(prefix="xteink-ingest-") as tmp:
        src = Path(tmp) / f"input{ext}"
        out = Path(tmp) / "output.epub"
        src.write_bytes(data)
        argv = [
            pandoc,
            "--sandbox",
            "-f",
            _PANDOC_FROM[ext],
            "-t",
            "epub",
            "--metadata",
            f"title={title}",
        ]
        if author:
            argv += ["--metadata", f"author={author}"]
        argv += ["-o", str(out), str(src)]
        try:
            proc = subprocess.run(  # nosec B603 - shell=False, argv list, no URLs
                argv,
                shell=False,
                capture_output=True,
                timeout=limits.convert_timeout_s,
                check=False,
                stdin=subprocess.DEVNULL,
            )
        except subprocess.TimeoutExpired as exc:
            raise IngestError("conversion timed out", "conversion_timeout") from exc
        except OSError as exc:
            raise IngestEnvironmentError(f"cannot run pandoc: {exc}") from exc
        if proc.returncode != 0 or not out.is_file():
            raise IngestError("conversion failed", "conversion_failed")
        result = out.read_bytes()
    if len(result) > limits.max_bytes or not _check_epub(result, limits):
        raise IngestError("converter produced an invalid EPUB", "conversion_failed")
    return result


def ingest(
    data: bytes,
    *,
    filename: str,
    title: str | None = None,
    author: str = "",
    kind: str | None = None,
    limits: IngestLimits = DEFAULT_LIMITS,
) -> PreparedUpload:
    """Validate (and convert) an upload. Raises :class:`IngestError` on refusal."""
    if len(data) > limits.max_bytes:
        raise IngestError("file exceeds the size limit", "too_large")
    if not data:
        raise IngestError("file is empty", "bad_magic")
    ext = os.path.splitext(filename or "")[1].lower()
    stem = os.path.splitext(os.path.basename(filename or ""))[0] or "Untitled"
    final_title = (title or "").strip() or stem

    if data.startswith(PDF_MAGIC):
        raise IngestError("PDF is not supported yet", "pdf_not_supported")

    if ext in MARKUP_EXTENSIONS:
        if not _is_text(data):
            raise IngestError("file is not valid UTF-8 text", "bad_magic")
        epub = _convert(data, ext, final_title, author, limits)
        return PreparedUpload(epub, "epub", kind or "article", final_title, author)

    if ext == ".epub":
        if not _check_epub(data, limits):
            raise IngestError("not a valid EPUB", "bad_magic")
        return PreparedUpload(data, "epub", kind or "book", final_title, author)
    if ext == ".bmp":
        if not data.startswith(BMP_MAGIC):
            raise IngestError("not a valid BMP", "bad_magic")
        return PreparedUpload(data, "bmp", kind or "book", final_title, author)
    if ext == ".txt":
        if not _is_text(data):
            raise IngestError("not valid UTF-8 text", "bad_magic")
        return PreparedUpload(data, "txt", kind or "book", final_title, author)
    raise IngestError(f"unsupported file type {ext or '(none)'}", "unsupported_format")


def ingest_and_add(
    library: LibraryService,
    data: bytes,
    *,
    filename: str,
    title: str | None = None,
    author: str = "",
    kind: str | None = None,
    limits: IngestLimits = DEFAULT_LIMITS,
) -> AddResult:
    """Ingest an upload and store it via the library."""
    p = ingest(data, filename=filename, title=title, author=author, kind=kind, limits=limits)
    return library.add(p.data, title=p.title, kind=p.kind, format=p.format, author=p.author)
