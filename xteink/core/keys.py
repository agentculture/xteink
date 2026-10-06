"""Key generation/verification. Only sha256 hashes + a prefix id are stored."""

from __future__ import annotations

import hashlib
import hmac
import secrets

from .errors import AuthError, NotFoundError
from .models import ApiKey
from .store import Store, now


def generate_key(prefix: str) -> tuple[str, str, str]:
    """Return (raw_key, key_id, key_hash). Raw key format: ``<prefix>_<key_id>_<secret>``."""
    key_id = secrets.token_hex(4)
    raw = f"{prefix}_{key_id}_{secrets.token_urlsafe(32)}"
    return raw, key_id, hash_key(raw)


def hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def parse_key(raw: str, prefix: str) -> str:
    """Return the key_id from a raw key or raise AuthError."""
    parts = raw.split("_", 2) if isinstance(raw, str) else []
    if len(parts) != 3 or parts[0] != prefix or not parts[1] or not parts[2]:
        raise AuthError("invalid key")
    return parts[1]


def verify(raw: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_key(raw), stored_hash)


class KeyService:
    """Non-device API keys (``xtk_`` prefix) for the HTTP API / MCP."""

    PREFIX = "xtk"

    def __init__(self, store: Store) -> None:
        self.store = store

    @staticmethod
    def _row(r) -> ApiKey:
        return ApiKey(
            r["id"], r["name"], r["key_id"], r["created_at"], r["revoked_at"], r["last_used"]
        )

    def create(self, name: str) -> tuple[ApiKey, str]:
        raw, key_id, key_hash = generate_key(self.PREFIX)
        with self.store.connect() as c:
            cur = c.execute(
                "INSERT INTO api_keys (name, key_id, key_hash, created_at) VALUES (?, ?, ?, ?)",
                (name, key_id, key_hash, now()),
            )
            row = c.execute("SELECT * FROM api_keys WHERE id = ?", (cur.lastrowid,)).fetchone()
        return self._row(row), raw

    def authenticate(self, raw: str) -> ApiKey:
        key_id = parse_key(raw, self.PREFIX)
        with self.store.connect() as c:
            row = c.execute("SELECT * FROM api_keys WHERE key_id = ?", (key_id,)).fetchone()
            if row is None or row["revoked_at"] or not verify(raw, row["key_hash"]):
                raise AuthError("invalid key")
            c.execute("UPDATE api_keys SET last_used = ? WHERE id = ?", (now(), row["id"]))
            row = c.execute("SELECT * FROM api_keys WHERE id = ?", (row["id"],)).fetchone()
        return self._row(row)

    def revoke(self, api_key_id: int) -> None:
        with self.store.connect() as c:
            cur = c.execute("UPDATE api_keys SET revoked_at = ? WHERE id = ?", (now(), api_key_id))
            if cur.rowcount == 0:
                raise NotFoundError(f"api key {api_key_id} not found")

    def list(self) -> list[ApiKey]:
        with self.store.connect() as c:
            return [self._row(r) for r in c.execute("SELECT * FROM api_keys ORDER BY id")]
