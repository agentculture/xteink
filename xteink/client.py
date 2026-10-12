"""Stdlib-only client for the xteink HTTP API (shared by the CLI and the MCP server).

Configuration comes from the environment: ``XTEINK_URL`` (default
``http://127.0.0.1:8780``) and ``XTEINK_API_KEY``. The key is sent as a bearer token and is
never included in error messages or reprs.
"""

from __future__ import annotations

import json
import mimetypes
import os
import secrets
import urllib.error
import urllib.parse
import urllib.request  # nosec B404 - scheme is restricted to http/https below
from pathlib import Path
from typing import Any, Mapping

URL_ENV = "XTEINK_URL"
KEY_ENV = "XTEINK_API_KEY"
DEFAULT_URL = "http://127.0.0.1:8780"
DEFAULT_TIMEOUT = 60.0

__all__ = [
    "ApiError",
    "AuthenticationError",
    "Client",
    "ConfigError",
    "ServerUnreachable",
    "from_env",
]


class ApiError(Exception):
    """The API answered with an error status."""

    def __init__(self, status: int, code: str, detail: str) -> None:
        super().__init__(f"{status} {code}: {detail}")
        self.status = status
        self.code = code
        self.detail = detail


class AuthenticationError(ApiError):
    """401: the API key is missing, invalid or revoked."""


class ServerUnreachable(ApiError):
    """The server could not be reached (connection refused, DNS, timeout)."""

    def __init__(self, detail: str) -> None:
        super().__init__(0, "server_unreachable", detail)


class ConfigError(Exception):
    """Client configuration is unusable (e.g. XTEINK_API_KEY unset)."""


def _check_url(url: str) -> str:
    url = url.strip().rstrip("/")
    if urllib.parse.urlsplit(url).scheme not in ("http", "https"):
        raise ConfigError(f"{URL_ENV} must be an http(s) URL")
    return url


def _multipart(fields: Mapping[str, str], filename: str, data: bytes) -> tuple[bytes, str]:
    boundary = "----xteink" + secrets.token_hex(16)
    ctype = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    safe = filename.replace('"', "_").replace("\r", "_").replace("\n", "_")
    parts: list[bytes] = []
    for name, value in fields.items():
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'.encode()
            + value.encode("utf-8")
            + b"\r\n"
        )
    parts.append(
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
            f'filename="{safe}"\r\nContent-Type: {ctype}\r\n\r\n'
        ).encode()
        + data
        + b"\r\n"
    )
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


class Client:
    def __init__(
        self, base_url: str = DEFAULT_URL, api_key: str = "", timeout: float = DEFAULT_TIMEOUT
    ) -> None:
        self.base_url = _check_url(base_url)
        self._api_key = api_key
        self.timeout = timeout

    def __repr__(self) -> str:
        return f"Client(base_url={self.base_url!r})"

    # -- transport ---------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        *,
        query: Mapping[str, Any] | None = None,
        json_body: Any = None,
        raw_body: bytes | None = None,
        content_type: str | None = None,
    ) -> Any:
        if not self._api_key:
            raise AuthenticationError(401, "missing_key", f"{KEY_ENV} is not set")
        url = self.base_url + path
        if query:
            q = {k: v for k, v in query.items() if v is not None}
            if q:
                url += "?" + urllib.parse.urlencode(q)
        headers = {"Authorization": f"Bearer {self._api_key}", "Accept": "application/json"}
        body = raw_body
        if json_body is not None:
            body = json.dumps(json_body).encode()
            content_type = "application/json"
        if content_type:
            headers["Content-Type"] = content_type
        req = urllib.request.Request(url, data=body, method=method, headers=headers)  # nosec B310
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # nosec B310
                payload = resp.read()
        except urllib.error.HTTPError as exc:
            raise self._error(exc.code, exc.read()) from None
        except OSError as exc:  # includes URLError
            reason = getattr(exc, "reason", exc)
            raise ServerUnreachable(f"cannot reach {self.base_url}: {reason}") from None
        return json.loads(payload) if payload else None

    @staticmethod
    def _error(status: int, raw: bytes) -> ApiError:
        code, detail = "", ""
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                code = str(data.get("code") or "")
                d = data.get("detail", "")
                detail = d if isinstance(d, str) else json.dumps(d)
        except ValueError:
            detail = raw.decode("utf-8", "replace")[:200]
        if status == 401:
            return AuthenticationError(status, code or "unauthorized", detail or "unauthorized")
        return ApiError(status, code or f"http_{status}", detail or "request failed")

    # -- library -----------------------------------------------------------

    def list_library(
        self, q: str | None = None, kind: str | None = None, limit: int = 100, offset: int = 0
    ) -> list[dict]:
        data = self._request(
            "GET",
            "/api/library",
            query={"q": q, "kind": kind, "limit": limit, "offset": offset},
        )
        return data["items"]

    def get_item(self, item_id: int) -> dict:
        return self._request("GET", f"/api/library/{int(item_id)}")

    def upload(
        self,
        data: bytes | None = None,
        filename: str = "",
        title: str | None = None,
        author: str = "",
        kind: str | None = None,
        *,
        path: str | os.PathLike | None = None,
    ) -> dict:
        """Upload bytes (``data``) or a local file (``path``); returns ``{item, created}``."""
        if (data is None) == (path is None):
            raise ValueError("give exactly one of data or path")
        if path is not None:
            p = Path(path)
            data = p.read_bytes()
            filename = filename or p.name
        if not filename:
            raise ValueError("filename is required")
        fields = {"author": author}
        if title is not None:
            fields["title"] = title
        if kind is not None:
            fields["kind"] = kind
        body, ctype = _multipart(fields, filename, data)  # type: ignore[arg-type]
        return self._request("POST", "/api/library", raw_body=body, content_type=ctype)

    def delete_item(self, item_id: int) -> None:
        self._request("DELETE", f"/api/library/{int(item_id)}")

    # -- devices -----------------------------------------------------------

    def list_devices(self) -> list[dict]:
        return self._request("GET", "/api/devices")["devices"]

    def register_device(self, name: str, *, mirror: bool = False) -> dict:
        """Register a reader; returns ``{device, key}`` with the raw device key (shown once)."""
        return self._request("POST", "/api/devices", json_body={"name": name, "mirror": mirror})

    def revoke_device(self, device_id: int) -> dict:
        """Revoke a reader's key; its next sync gets 401."""
        return self._request("POST", f"/api/devices/{int(device_id)}/revoke")

    def queue_item(self, device_id: int, item_id: int) -> dict:
        return self._request(
            "POST", f"/api/devices/{int(device_id)}/queue", json_body={"item_id": int(item_id)}
        )

    def device_queue(self, device_id: int, state: str = "queued") -> list[dict]:
        return self._request("GET", f"/api/devices/{int(device_id)}/queue", query={"state": state})[
            "entries"
        ]


def from_env(env: Mapping[str, str] | None = None) -> Client:
    """Build a client from ``XTEINK_URL`` / ``XTEINK_API_KEY``; raises ConfigError if no key."""
    env = os.environ if env is None else env
    key = (env.get(KEY_ENV) or "").strip()
    if not key:
        raise ConfigError(
            f"{KEY_ENV} is not set; mint a key with 'python -m xteink.server create-key NAME'"
        )
    return Client((env.get(URL_ENV) or DEFAULT_URL).strip() or DEFAULT_URL, key)
