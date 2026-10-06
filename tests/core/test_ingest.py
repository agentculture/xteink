import io
import os
import shutil
import stat
import sys
import zipfile
from pathlib import Path

import pytest

from xteink.core import CoreError
from xteink.core.ingest import (
    IngestEnvironmentError,
    IngestError,
    IngestLimits,
    ingest,
    ingest_and_add,
)

FIX = Path(__file__).parent.parent / "fixtures" / "ingest"


def make_epub(extra=None, first="mimetype", mimetype=b"application/epub+zip") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
        z.writestr(first, mimetype)
        z.writestr("META-INF/container.xml", "<container/>")
        for name, content in (extra or {}).items():
            z.writestr(name, content, compress_type=zipfile.ZIP_DEFLATED)
    return buf.getvalue()


def fake_pandoc(tmp_path, monkeypatch, body: str):
    d = tmp_path / "bin"
    d.mkdir()
    p = d / "pandoc"
    p.write_text(f"#!{sys.executable}\n" + body)
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", str(d))
    return d


WRITE_EPUB = """
import sys, zipfile
a = sys.argv
out = a[a.index("-o") + 1]
open(%r, "w").write(" ".join(a))
with zipfile.ZipFile(out, "w") as z:
    z.writestr("mimetype", "application/epub+zip")
"""


def test_ingest_error_is_core_error():
    assert issubclass(IngestError, CoreError)
    assert issubclass(IngestEnvironmentError, IngestError)
    assert IngestEnvironmentError("x").code == "converter_missing"


def test_oversized_rejected():
    with pytest.raises(IngestError) as e:
        ingest(b"a" * 20, filename="a.txt", limits=IngestLimits(max_bytes=10))
    assert e.value.code == "too_large"


def test_wrong_magic():
    for name, data in [("a.epub", b"not a zip"), ("a.bmp", b"XXnope"), ("a.txt", b"\x00\x01")]:
        with pytest.raises(IngestError) as e:
            ingest(data, filename=name)
        assert e.value.code == "bad_magic"
    with pytest.raises(IngestError) as e:
        ingest(make_epub(first="other"), filename="a.epub")
    assert e.value.code == "bad_magic"
    with pytest.raises(IngestError) as e:
        ingest((FIX / "bad.md").read_bytes(), filename="bad.md")
    assert e.value.code == "bad_magic"


def test_zip_bomb_uncompressed_size():
    data = make_epub({"big.txt": b"\x00" * (5 * 1024 * 1024)})
    assert len(data) < 100_000
    with pytest.raises(IngestError) as e:
        ingest(data, filename="b.epub", limits=IngestLimits(max_uncompressed_bytes=1024 * 1024))
    assert e.value.code == "zip_bomb"


def test_zip_bomb_entry_count():
    data = make_epub({f"f{i}.txt": b"x" for i in range(50)})
    with pytest.raises(IngestError) as e:
        ingest(data, filename="b.epub", limits=IngestLimits(max_zip_entries=10))
    assert e.value.code == "zip_bomb"


def test_passthrough_unchanged():
    epub = make_epub()
    r = ingest(epub, filename="My Book.epub", author="A")
    assert (r.data, r.format, r.kind, r.title, r.author) == (epub, "epub", "book", "My Book", "A")
    for name, fmt in [("note.txt", "txt"), ("pic.bmp", "bmp")]:
        raw = (FIX / name).read_bytes()
        r = ingest(raw, filename=name, title="T")
        assert r.data == raw and r.format == fmt and r.title == "T"


def test_pdf_rejected():
    with pytest.raises(IngestError) as e:
        ingest((FIX / "doc.pdf").read_bytes(), filename="doc.pdf")
    assert e.value.code == "pdf_not_supported"
    assert "not supported yet" in str(e.value)


def test_unsupported_extension():
    with pytest.raises(IngestError) as e:
        ingest(b"x", filename="a.exe")
    assert e.value.code == "unsupported_format"


@pytest.mark.parametrize("name", ["article.md", "article.html"])
def test_markup_converts_via_pandoc(tmp_path, monkeypatch, name):
    log = tmp_path / "argv.txt"
    fake_pandoc(tmp_path, monkeypatch, WRITE_EPUB % str(log))
    r = ingest((FIX / name).read_bytes(), filename=name, title="Title", author="Au")
    assert (r.format, r.kind, r.title, r.author) == ("epub", "article", "Title", "Au")
    assert zipfile.ZipFile(io.BytesIO(r.data)).read("mimetype") == b"application/epub+zip"
    argv = log.read_text()
    assert "title=Title" in argv and "author=Au" in argv and "--sandbox" in argv
    assert "http" not in argv


def test_missing_pandoc(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))
    with pytest.raises(IngestEnvironmentError) as e:
        ingest(b"# hi", filename="a.md")
    assert e.value.code == "converter_missing"


def test_pandoc_timeout(tmp_path, monkeypatch):
    fake_pandoc(tmp_path, monkeypatch, "import time\ntime.sleep(30)\n")
    with pytest.raises(IngestError) as e:
        ingest(b"# hi", filename="a.md", limits=IngestLimits(convert_timeout_s=0.5))
    assert e.value.code == "conversion_timeout"


def test_pandoc_nonzero(tmp_path, monkeypatch):
    fake_pandoc(tmp_path, monkeypatch, "import sys\nsys.exit(3)\n")
    with pytest.raises(IngestError) as e:
        ingest(b"# hi", filename="a.md")
    assert e.value.code == "conversion_failed"


def test_pandoc_garbage_output(tmp_path, monkeypatch):
    body = 'import sys\na=sys.argv\nopen(a[a.index("-o")+1],"w").write("junk")\n'
    fake_pandoc(tmp_path, monkeypatch, body)
    with pytest.raises(IngestError) as e:
        ingest(b"# hi", filename="a.md")
    assert e.value.code == "conversion_failed"


def test_ingest_and_add_stores_article(tmp_path, monkeypatch, library):
    fake_pandoc(tmp_path, monkeypatch, WRITE_EPUB % str(tmp_path / "log"))
    res = ingest_and_add(library, b"# hi", filename="a.md", title="T")
    assert res.created and res.item.kind == "article" and res.item.format == "epub"


@pytest.mark.skipif(shutil.which("pandoc") is None, reason="pandoc not installed")
def test_real_pandoc():
    r = ingest((FIX / "article.md").read_bytes(), filename="article.md", title="Real", author="X")
    assert r.format == "epub" and r.data.startswith(b"PK")
    assert os.path.exists(FIX / "article.md")
