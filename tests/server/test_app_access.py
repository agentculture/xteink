"""Cloudflare Access SSO on the main app: a verified ``Cf-Access-Jwt-Assertion`` is enough.

* main app + Access configured: a valid JWT authenticates every ``/api`` route as an operator;
  a bad one is a 401; a Bearer key keeps working exactly as before (and, when sent, decides).
* device app: never accepts an Access JWT, configured or not (device keys only).
* privacy: no JWKS fetch at startup, without a JWT, or with Access unset.
"""

from __future__ import annotations

import logging

import pytest

from xteink.core import DeviceService, KeyService

from .access_jwt import AUD, NOW, TEAM, Keypair, claims, jwks, keypair, now, token
from .conftest import bearer

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from xteink.server.access import ACCESS_HEADER, CSRF_HEADER, AccessVerifier  # noqa: E402
from xteink.server.app import create_app, create_apps, create_device_app  # noqa: E402

ROUTES = ["/api/library", "/api/library?limit=1", "/api/devices", "/api/keys", "/api/whoami"]


def sso(tok: str | None = None) -> dict:
    return {ACCESS_HEADER: tok if tok is not None else token()}


class Fetches:
    """A fake JWKS endpoint that counts how often it is asked."""

    def __init__(self, keyset=None) -> None:
        self.count = 0
        self.keyset = keyset

    def __call__(self):
        self.count += 1
        return self.keyset if self.keyset is not None else jwks()


@pytest.fixture
def fetches():
    return Fetches()


@pytest.fixture
def verifier(fetches):
    return AccessVerifier(TEAM, AUD, fetch_jwks=fetches, clock=now)


@pytest.fixture
def sso_client(store, verifier):
    return TestClient(create_app(store, access=verifier))


# --- a valid Access JWT is enough on the main app --------------------------------------------


@pytest.mark.parametrize("path", ROUTES)
def test_valid_access_jwt_authenticates_main_api(sso_client, path):
    assert sso_client.get(path, headers=sso()).status_code == 200


def test_whoami_reports_access_identity(sso_client):
    r = sso_client.get("/api/whoami", headers=sso())
    assert r.json() == {"via": "access", "identity": "alice@example.com"}


def test_whoami_reports_key_identity(sso_client, store):
    _, raw = KeyService(store).create("laptop")
    r = sso_client.get("/api/whoami", headers=bearer(raw))
    assert r.json() == {"via": "key", "identity": "laptop"}


def test_whoami_needs_auth(sso_client, main_client):
    assert sso_client.get("/api/whoami").status_code == 401
    assert main_client.get("/api/whoami").status_code == 401


def test_access_operator_can_manage_devices_and_keys(sso_client, store):
    h = {**sso(), CSRF_HEADER: "1"}
    r = sso_client.post("/api/devices", json={"name": "r1"}, headers=h)
    assert r.status_code == 201
    r = sso_client.post("/api/keys", json={"name": "phone"}, headers=h)
    assert r.status_code == 201
    assert [k.name for k in KeyService(store).list()] == ["phone"]


@pytest.mark.parametrize(
    "body,expected",
    [
        (claims(aud=["someone-else"]), "bad_audience"),
        (claims(iss="https://evil.cloudflareaccess.example"), "bad_issuer"),
        (claims(exp=NOW - 3600), "expired"),
        (claims(nbf=NOW + 3600), "not_yet_valid"),
    ],
)
def test_invalid_claims_are_401(sso_client, caplog, body, expected):
    caplog.set_level(logging.INFO, logger="xteink.server.access")
    tok = token(body)
    r = sso_client.get("/api/library", headers=sso(tok))
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"
    assert expected in caplog.text
    assert tok not in caplog.text and tok not in r.text


def test_bad_signature_is_401(sso_client):
    forged = token(pair=Keypair(kid="kid-1", seed="forger"))
    assert sso_client.get("/api/library", headers=sso(forged)).status_code == 401


def test_unknown_kid_is_401(sso_client):
    other = token(pair=keypair("kid-other"))
    assert sso_client.get("/api/library", headers=sso(other)).status_code == 401


@pytest.mark.parametrize("bad", ["", "garbage", "a.b.c"])
def test_malformed_jwt_is_401(sso_client, bad):
    assert sso_client.get("/api/library", headers=sso(bad)).status_code == 401


def test_success_logs_identity_not_token(sso_client, caplog):
    caplog.set_level(logging.INFO, logger="xteink.server.access")
    tok = token()
    assert sso_client.get("/api/library", headers=sso(tok)).status_code == 200
    assert "alice@example.com" in caplog.text
    assert tok not in caplog.text
    assert tok.split(".")[2] not in caplog.text


def test_cf_authorization_cookie_alone_is_not_accepted(store, verifier, fetches):
    """Header only: the edge adds it on every Access-proxied request; the cookie adds nothing."""
    client = TestClient(create_app(store, access=verifier), cookies={"CF_Authorization": token()})
    assert client.get("/api/library").status_code == 401
    assert fetches.count == 0


# --- CSRF: an ambient SSO session needs a custom header on unsafe methods --------------------


@pytest.mark.parametrize(
    "method,path,kw",
    [
        ("post", "/api/keys", {"json": {"name": "x"}}),
        ("post", "/api/keys/1/revoke", {}),
        ("post", "/api/devices/1/revoke", {}),
        ("delete", "/api/library/1", {}),
    ],
)
def test_access_unsafe_method_without_csrf_header_is_403(sso_client, method, path, kw):
    r = getattr(sso_client, method)(path, headers=sso(), **kw)
    assert r.status_code == 403


def test_bearer_unsafe_method_needs_no_csrf_header(sso_client, api_key):
    r = sso_client.post("/api/keys", json={"name": "x"}, headers=bearer(api_key))
    assert r.status_code == 201


# --- Bearer keys are unchanged -----------------------------------------------------------------


@pytest.mark.parametrize("path", ROUTES)
def test_bearer_key_still_works_with_access_configured(sso_client, api_key, fetches, path):
    assert sso_client.get(path, headers=bearer(api_key)).status_code == 200
    assert fetches.count == 0


def test_invalid_bearer_is_401_even_with_a_valid_jwt(sso_client):
    """An explicit Bearer credential decides; it is never silently swapped for the JWT."""
    h = {**sso(), **bearer("xtk_deadbeef_wrong")}
    assert sso_client.get("/api/library", headers=h).status_code == 401


def test_device_key_is_still_refused_on_main_app(sso_client, device_key):
    assert sso_client.get("/api/library", headers=bearer(device_key)).status_code == 401


def test_no_credentials_is_401(sso_client, fetches):
    r = sso_client.get("/api/library")
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"
    assert fetches.count == 0


# --- the device app never accepts Access JWTs -------------------------------------------------


def test_device_app_ignores_access_jwt(store, verifier, fetches):
    _, device = create_apps(store, access=verifier)
    dc = TestClient(device)
    assert dc.get("/api/device/whoami", headers=sso()).status_code == 401
    assert dc.get("/api/device/queue", headers=sso()).status_code == 401
    assert dc.post("/api/device/ack", json={}, headers=sso()).status_code == 401
    assert fetches.count == 0


def test_device_app_factory_takes_no_access_verifier():
    import inspect

    assert "access" not in inspect.signature(create_device_app).parameters


def test_device_key_still_works_on_device_app_when_access_configured(store, verifier):
    _, device = create_apps(store, access=verifier)
    _, raw = DeviceService(store).register("reader")
    dc = TestClient(device)
    assert dc.get("/api/device/whoami", headers={**sso(), **bearer(raw)}).status_code == 200


def test_main_and_device_share_store_with_access(store, verifier):
    main, device = create_apps(store, access=verifier)
    mc, dc = TestClient(main), TestClient(device)
    r = mc.post("/api/devices", json={"name": "r1"}, headers={**sso(), CSRF_HEADER: "1"})
    assert r.status_code == 201
    assert dc.get("/api/device/whoami", headers=bearer(r.json()["key"])).status_code == 200


# --- privacy: the JWKS fetch is lazy and never happens with Access unset ---------------------


def test_no_fetch_at_startup_or_without_a_jwt(store, verifier, fetches, api_key):
    client = TestClient(create_app(store, access=verifier))
    client.get("/")
    client.get("/api/library")
    client.get("/api/library", headers=bearer(api_key))
    assert fetches.count == 0
    client.get("/api/library", headers=sso())
    assert fetches.count == 1
    client.get("/api/library", headers=sso())
    assert fetches.count == 1  # cached by kid


def test_access_unset_ignores_jwt_and_never_fetches(monkeypatch, main_client):
    import xteink.server.access as access

    calls: list = []
    monkeypatch.setattr(access.urllib.request, "urlopen", lambda *a, **k: calls.append(a))
    r = main_client.get("/api/library", headers=sso())
    assert r.status_code == 401
    assert calls == []


def test_serve_builds_no_verifier_when_access_unset(monkeypatch):
    """The production wiring: Access off -> the main app has no verifier at all."""
    from xteink.server import app as app_mod
    from xteink.server import load_config

    built: dict = {}
    real = app_mod.create_apps

    def spy(store=None, *, access=None):
        built["access"] = access
        return real(store, access=access)

    monkeypatch.setattr(app_mod, "create_apps", spy)
    app_mod.build_apps(load_config({}))
    assert built["access"] is None
    app_mod.build_apps(load_config({"XTEINK_ACCESS_TEAM_DOMAIN": TEAM, "XTEINK_ACCESS_AUD": AUD}))
    assert isinstance(built["access"], AccessVerifier)
