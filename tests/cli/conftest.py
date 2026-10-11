"""A stdlib stub of the xteink HTTP API that records every request (no network, no extras)."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

KEY = "xk_test_secret"

ITEMS = {
    1: {
        "id": 1,
        "kind": "book",
        "title": "Dune",
        "author": "Herbert",
        "format": "epub",
        "size": 10,
    },
    2: {"id": 2, "kind": "article", "title": "Essay", "author": "", "format": "epub", "size": 5},
}
DEVICES = [
    {"id": 1, "name": "Reader One", "revoked_at": None, "last_seen": None, "mirror": False},
    {"id": 2, "name": "Reader Two", "revoked_at": None, "last_seen": None, "mirror": True},
]
FIRMWARE = [
    {
        "id": 1,
        "version": "1.6.5-dev",
        "sha256": "ab" * 32,
        "size": 64,
        "board": "x4",
        "fork_commit": "abc123",
        "source_pr": "https://example.test/pr/1",
        "created_at": "2026-10-11T00:00:00+00:00",
    }
]
IMAGE = {"size": 64, "board": "x4", "chip_id": 5, "version": "1.6.5-dev"}


class FakeApi:
    def __init__(self) -> None:
        self.requests: list[tuple[str, str]] = []
        self.bodies: list[bytes] = []
        self.devices = [dict(d) for d in DEVICES]
        self.main_url = ""
        self.device_url = ""

    @property
    def writes(self) -> list[tuple[str, str]]:
        return [r for r in self.requests if r[0] != "GET"]


def _handler(api: FakeApi, device_app: bool):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):  # silence
            pass

        def _send(self, status: int, body=None):
            raw = json.dumps(body).encode() if body is not None else b""
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def _route(self, method: str):
            path = self.path.split("?")[0]
            n = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(n) if n else b""
            api.bodies.append(body)
            api.requests.append((method, self.path))
            if device_app:
                return self._send(401, {"detail": "no key", "code": "unauthorized"})
            if path == "/":
                return self._send(200, {"ok": True})
            if self.headers.get("Authorization") != f"Bearer {KEY}":
                return self._send(401, {"detail": "bad key", "code": "unauthorized"})
            if method == "GET" and path == "/api/library":
                return self._send(200, {"items": list(ITEMS.values())})
            if method == "POST" and path == "/api/library":
                return self._send(201, {"item": ITEMS[1], "created": True})
            if path.startswith("/api/library/"):
                iid = int(path.rsplit("/", 1)[1])
                if iid not in ITEMS:
                    return self._send(404, {"detail": "not found", "code": "not_found"})
                if method == "GET":
                    return self._send(200, ITEMS[iid])
                if method == "DELETE":
                    return self._send(204)
            if method == "GET" and path == "/api/devices":
                return self._send(200, {"devices": api.devices})
            if method == "GET" and path == "/api/firmware":
                return self._send(200, {"firmware": FIRMWARE})
            if method == "POST" and path == "/api/firmware":
                if b"BADIMAGE" in body:
                    msg = {"detail": "not an ESP image: bad magic byte", "code": "bad_magic"}
                    return self._send(422, msg)
                if b'name="dry_run"\r\n\r\ntrue' in body:
                    return self._send(200, {"dry_run": True, "image": IMAGE})
                return self._send(201, {"firmware": FIRMWARE[0], "created": True, "image": IMAGE})
            if method == "POST" and path.endswith("/offer"):
                req = json.loads(body)
                if req.get("device_id") == 2:
                    msg = {"detail": "device 2 rolled back firmware 1", "code": "http_422"}
                    return self._send(422, msg)
                offered = [1, 2] if req.get("all") else [req["device_id"]]
                return self._send(
                    200,
                    {
                        "firmware": FIRMWARE[0],
                        "dry_run": req["dry_run"],
                        "offered": offered,
                        "skipped_revoked": [],
                        "skipped_rolled_back": [],
                    },
                )
            if method == "POST" and path.endswith("/queue"):
                return self._send(201, {"device_id": 1, "item_id": 1, "state": "queued"})
            if method == "POST" and path.endswith("/revoke"):
                return self._send(200, {**DEVICES[0], "revoked_at": "now"})
            return self._send(404, {"detail": "nope", "code": "not_found"})

        do_GET = lambda self: self._route("GET")  # noqa: E731
        do_POST = lambda self: self._route("POST")  # noqa: E731
        do_DELETE = lambda self: self._route("DELETE")  # noqa: E731

    return H


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch):
    fake = FakeApi()
    servers = []
    for is_device in (False, True):
        srv = ThreadingHTTPServer(("127.0.0.1", 0), _handler(fake, is_device))
        threading.Thread(
            target=srv.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True
        ).start()
        servers.append(srv)
    fake.main_url = f"http://127.0.0.1:{servers[0].server_port}"
    fake.device_url = f"http://127.0.0.1:{servers[1].server_port}"
    monkeypatch.setenv("XTEINK_URL", fake.main_url)
    monkeypatch.setenv("XTEINK_DEVICE_URL", fake.device_url)
    monkeypatch.setenv("XTEINK_API_KEY", KEY)
    yield fake
    for s in servers:
        s.shutdown()
        s.server_close()
