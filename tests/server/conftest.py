"""Shared fixtures for the HTTP server suite (skips cleanly without the ``server`` extra)."""

import pytest

from xteink.core import DeviceService, KeyService, Store


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "data")


@pytest.fixture
def api_key(store):
    _, raw = KeyService(store).create("test")
    return raw


@pytest.fixture
def device_key(store):
    _, raw = DeviceService(store).register("reader")
    return raw


@pytest.fixture
def main_client(store):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from xteink.server.app import create_app

    return TestClient(create_app(store))


@pytest.fixture
def device_client(store):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from xteink.server.app import create_device_app

    return TestClient(create_device_app(store))


def bearer(raw: str) -> dict:
    return {"Authorization": f"Bearer {raw}"}
