import hashlib

import pytest

from xteink.core import NotFoundError, Store, ValidationError


def _add(library, data=b"hello", **kw):
    meta = dict(title="Dune", author="Frank Herbert", kind="book", format="epub")
    meta.update(kw)
    return library.add(data, **meta)


def test_data_dir_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("XTEINK_DATA_DIR", str(tmp_path / "envdata"))
    s = Store()
    assert s.data_dir == tmp_path / "envdata"
    assert (tmp_path / "envdata" / "files").is_dir()


def test_add_records_metadata(library):
    res = _add(library)
    item = res.item
    assert res.created is True
    assert item.sha256 == hashlib.sha256(b"hello").hexdigest()
    assert (item.kind, item.title, item.author, item.format, item.size) == (
        "book",
        "Dune",
        "Frank Herbert",
        "epub",
        5,
    )
    assert library.read_bytes(item.id) == b"hello"


def test_add_rejects_a_path(library, tmp_path):
    p = tmp_path / "a.txt"
    p.write_bytes(b"from path")
    with pytest.raises(ValidationError):
        library.add(p, title="A", kind="article", format="txt")
    with pytest.raises(ValidationError):
        library.add(str(p), title="A", kind="article", format="txt")


def test_dedup_by_sha256(library):
    first = _add(library)
    second = _add(library, title="Other title")
    assert second.created is False
    assert second.item.id == first.item.id
    assert len(library.list()) == 1


def test_kind_validated(library):
    with pytest.raises(ValidationError):
        _add(library, kind="comic")
    with pytest.raises(ValidationError):
        _add(library, title="  ")


def test_list_and_filter(library):
    _add(library, b"1", title="B1")
    _add(library, b"2", title="A1", kind="article", format="html")
    assert len(library.list()) == 2
    assert [i.title for i in library.list(kind="article")] == ["A1"]
    assert len(library.list(limit=1)) == 1
    assert len(library.list(limit=1, offset=1)) == 1


def test_get_and_missing(library):
    item = _add(library).item
    assert library.get(item.id) == item
    with pytest.raises(NotFoundError):
        library.get(999)


def test_delete_removes_row_and_file(library):
    item = _add(library).item
    path = library.file_path(item.id)
    assert path.exists()
    library.delete(item.id)
    assert not path.exists()
    with pytest.raises(NotFoundError):
        library.get(item.id)
    with pytest.raises(NotFoundError):
        library.delete(item.id)


def test_search_title_author_and_wildcards(library):
    _add(library, b"1", title="Dune", author="Frank Herbert")
    _add(library, b"2", title="100% Pure", author="Someone")
    assert [i.title for i in library.search("herbert")] == ["Dune"]
    assert [i.title for i in library.search("dun")] == ["Dune"]
    assert [i.title for i in library.search("100%")] == ["100% Pure"]
    assert library.search("%") == [i for i in library.list() if "%" in i.title]
    assert library.search("zzz") == []


def test_search_filters_kind_before_the_limit_and_honours_offset(library):
    for n in range(5):
        library.add(f"book {n}".encode(), title=f"The book {n}", kind="book", format="txt")
    art = library.add(b"article", title="The article", kind="article", format="txt").item
    assert [i.id for i in library.search("the", kind="article", limit=2)] == [art.id]
    first = library.search("the", kind="book", limit=2)
    second = library.search("the", kind="book", limit=2, offset=2)
    assert len(first) == 2
    assert len(second) == 2
    assert not {i.id for i in first} & {i.id for i in second}


def test_add_survives_a_concurrent_insert_of_the_same_bytes(library, monkeypatch):
    first = library.add(b"same", title="A", kind="book", format="txt").item
    real_connect = library.store.connect

    class MissFirstLookup:
        """The SELECT finds nothing, as if another upload had not committed yet."""

        def __init__(self, conn):
            self.conn, self.missed = conn, False

        def __enter__(self):
            self.inner = self.conn.__enter__()
            return self

        def __exit__(self, *exc):
            return self.conn.__exit__(*exc)

        def execute(self, sql, params=()):
            if "WHERE sha256 = ?" in sql and not self.missed:
                self.missed = True
                return self.inner.execute(sql, ("0" * 64,))
            return self.inner.execute(sql, params)

    monkeypatch.setattr(library.store, "connect", lambda: MissFirstLookup(real_connect()))
    again = library.add(b"same", title="B", kind="book", format="txt")
    assert again.created is False
    assert again.item.id == first.id
