"""LibraryService: deduplicated items + content-addressed files."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from .errors import NotFoundError, ValidationError
from .models import KINDS, AddResult, Item
from .store import Store, now

_SEL = "SELECT id, sha256, kind, title, author, format, size, created_at FROM items"


def _item(r) -> Item:
    return Item(**{k: r[k] for k in r.keys()})


def _like_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class LibraryService:
    def __init__(self, store: Store) -> None:
        self.store = store

    def add(
        self,
        data: bytes | str | os.PathLike[str],
        *,
        title: str,
        kind: str,
        format: str,  # noqa: A002 - public field name
        author: str = "",
    ) -> AddResult:
        """Add already-validated bytes (or a file path). Dedups by sha256."""
        if kind not in KINDS:
            raise ValidationError(f"kind must be one of {KINDS}")
        if not title or not title.strip():
            raise ValidationError("title is required")
        if not format or not format.strip():
            raise ValidationError("format is required")
        content = data if isinstance(data, bytes) else Path(data).read_bytes()
        sha = hashlib.sha256(content).hexdigest()
        with self.store.connect() as c:
            row = c.execute(_SEL + " WHERE sha256 = ?", (sha,)).fetchone()
            if row is not None:
                return AddResult(_item(row), False)
            blob = self.store.blob_path(sha)
            blob.parent.mkdir(parents=True, exist_ok=True)
            if not blob.exists():
                tmp = blob.with_suffix(".tmp")
                tmp.write_bytes(content)
                tmp.replace(blob)
            cur = c.execute(
                "INSERT INTO items (sha256, kind, title, author, format, size, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    sha,
                    kind,
                    title.strip(),
                    author.strip(),
                    format.strip().lower(),
                    len(content),
                    now(),
                ),
            )
            row = c.execute(_SEL + " WHERE id = ?", (cur.lastrowid,)).fetchone()
        return AddResult(_item(row), True)

    def get(self, item_id: int) -> Item:
        with self.store.connect() as c:
            row = c.execute(_SEL + " WHERE id = ?", (item_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"item {item_id} not found")
        return _item(row)

    def list(self, *, kind: str | None = None, limit: int = 100, offset: int = 0) -> list[Item]:
        sql = _SEL
        params: list = []
        if kind is not None:
            sql += " WHERE kind = ?"
            params.append(kind)
        sql += " ORDER BY id LIMIT ? OFFSET ?"
        params += [limit, offset]
        with self.store.connect() as c:
            return [_item(r) for r in c.execute(sql, params)]

    def search(self, query: str, *, limit: int = 100) -> list[Item]:
        pat = f"%{_like_escape(query.strip().lower())}%"
        with self.store.connect() as c:
            rows = c.execute(
                _SEL + " WHERE lower(title) LIKE ? ESCAPE '\\'"
                " OR lower(author) LIKE ? ESCAPE '\\' ORDER BY id LIMIT ?",
                (pat, pat, limit),
            )
            return [_item(r) for r in rows]

    def delete(self, item_id: int) -> None:
        """Remove the item, its queue entries (cascade) and its stored file."""
        item = self.get(item_id)
        with self.store.connect() as c:
            c.execute("DELETE FROM items WHERE id = ?", (item_id,))
        self.store.blob_path(item.sha256).unlink(missing_ok=True)

    def file_path(self, item_id: int) -> Path:
        return self.store.blob_path(self.get(item_id).sha256)

    def read_bytes(self, item_id: int) -> bytes:
        return self.file_path(item_id).read_bytes()
