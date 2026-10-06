"""Criterion 1+2: two apps, route isolation, key auth on every /api/* route."""

import pytest

from xteink.core import DeviceService, KeyService

from .conftest import bearer

pytest.importorskip("fastapi")

ADMIN_GETS = ["/api/library", "/api/library/1", "/api/devices", "/api/keys"]


# --- device app: only /api/device/* exists ---------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/api/library",
        "/api/library/1",
        "/api/devices",
        "/api/keys",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/index.html",
        "/api/device",
        "/api/device/nope",
    ],
)
def test_device_app_404_everywhere_else(device_client, api_key, path):
    r = device_client.get(path, headers=bearer(api_key))
    assert r.status_code == 404


def test_device_app_rejects_posts_to_admin(device_client, api_key):
    r = device_client.post("/api/keys", json={"name": "x"}, headers=bearer(api_key))
    assert r.status_code == 404


def test_device_app_has_no_library_routes_mounted():
    from xteink.server.app import create_device_app

    # openapi_url is None (not served), but the schema can still be generated in-process.
    paths = set(create_device_app().openapi()["paths"])
    assert paths and all(p.startswith("/api/device/") for p in paths), paths


def test_device_whoami_with_device_key(device_client, store):
    dev, raw = DeviceService(store).register("kitchen")
    r = device_client.get("/api/device/whoami", headers=bearer(raw))
    assert r.status_code == 200
    assert r.json() == {"id": dev.id, "name": "kitchen"}


def test_device_app_401_without_key(device_client):
    r = device_client.get("/api/device/whoami")
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"


def test_device_app_401_with_api_key(device_client, api_key):
    r = device_client.get("/api/device/whoami", headers=bearer(api_key))
    assert r.status_code == 401


def test_device_app_401_with_revoked_device_key(device_client, store):
    svc = DeviceService(store)
    dev, raw = svc.register("old")
    svc.revoke_key(dev.id)
    assert device_client.get("/api/device/whoami", headers=bearer(raw)).status_code == 401


def test_device_app_401_with_rotated_out_key(device_client, store):
    svc = DeviceService(store)
    dev, raw = svc.register("old")
    new = svc.rotate_key(dev.id)
    assert device_client.get("/api/device/whoami", headers=bearer(raw)).status_code == 401
    assert device_client.get("/api/device/whoami", headers=bearer(new)).status_code == 200


@pytest.mark.parametrize(
    "header",
    ["", "Bearer", "Bearer ", "Basic abc", "bearer xtd_a_b_c", "Bearer xtd_nope", "Token x"],
)
def test_device_app_401_malformed_header(device_client, header):
    r = device_client.get("/api/device/whoami", headers={"Authorization": header})
    assert r.status_code == 401


# --- main app: every /api/* needs an API key --------------------------------


@pytest.mark.parametrize("path", ADMIN_GETS)
def test_main_401_without_key(main_client, path):
    r = main_client.get(path)
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("path", ADMIN_GETS)
def test_main_401_with_device_key(main_client, device_key, path):
    assert main_client.get(path, headers=bearer(device_key)).status_code == 401


@pytest.mark.parametrize("path", ADMIN_GETS)
def test_main_401_with_revoked_key(main_client, store, path):
    svc = KeyService(store)
    key, raw = svc.create("gone")
    svc.revoke(key.id)
    assert main_client.get(path, headers=bearer(raw)).status_code == 401


def test_main_401_with_forged_key(main_client, api_key):
    prefix, key_id, _ = api_key.split("_", 2)
    forged = f"{prefix}_{key_id}_notthesecret"
    assert main_client.get("/api/keys", headers=bearer(forged)).status_code == 401


@pytest.mark.parametrize(
    "method,path",
    [
        ("post", "/api/library"),
        ("delete", "/api/library/1"),
        ("get", "/api/library/1/file"),
        ("post", "/api/devices"),
        ("get", "/api/devices/1"),
        ("post", "/api/devices/1/revoke"),
        ("post", "/api/devices/1/rotate"),
        ("put", "/api/devices/1/mirror"),
        ("get", "/api/devices/1/queue"),
        ("post", "/api/devices/1/queue"),
        ("post", "/api/keys"),
        ("post", "/api/keys/1/revoke"),
    ],
)
def test_main_every_api_route_needs_key(main_client, method, path):
    assert getattr(main_client, method)(path).status_code == 401


def test_every_main_api_route_is_auth_gated():
    """Structural check: every /api operation on the main app declares bearer security."""
    from xteink.server.app import create_app

    paths = create_app().openapi()["paths"]
    ops = [
        (path, method, op)
        for path, item in paths.items()
        if path.startswith("/api")
        for method, op in item.items()
    ]
    assert len(ops) >= 15
    for path, method, op in ops:
        assert op.get("security") == [{"HTTPBearer": []}], (method, path)


def test_main_app_has_no_device_routes(main_client, device_key):
    assert main_client.get("/api/device/whoami", headers=bearer(device_key)).status_code == 404


def test_main_valid_key_ok(main_client, api_key):
    assert main_client.get("/api/keys", headers=bearer(api_key)).status_code == 200


def test_401_body_does_not_echo_key(main_client):
    raw = "xtk_deadbeef_supersecretvalue"
    r = main_client.get("/api/keys", headers=bearer(raw))
    assert r.status_code == 401
    assert "supersecretvalue" not in r.text


# --- web assets at / (open, no key) ----------------------------------------


def test_root_placeholder_is_open(main_client):
    r = main_client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "xteink" in r.text


def test_root_serves_packaged_assets(tmp_path, store):
    from fastapi.testclient import TestClient

    from xteink.server.app import create_app

    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<html>REAL UI</html>")
    (web / "app.js").write_text("console.log(1)")
    c = TestClient(create_app(store, webassets_dir=web))
    assert "REAL UI" in c.get("/").text
    assert c.get("/app.js").status_code == 200
    assert c.get("/api/keys").status_code == 401  # API still wins over static mount


def test_main_docs_available_on_lan(main_client):
    assert main_client.get("/openapi.json").status_code == 200


def test_apps_share_one_store(store):
    from fastapi.testclient import TestClient

    from xteink.server.app import create_apps

    main, device = create_apps(store)
    mc, dc = TestClient(main), TestClient(device)
    _, admin = KeyService(store).create("admin")
    r = mc.post("/api/devices", json={"name": "r1"}, headers=bearer(admin))
    assert r.status_code == 201
    raw = r.json()["key"]
    assert dc.get("/api/device/whoami", headers=bearer(raw)).json()["name"] == "r1"
