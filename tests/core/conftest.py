"""Shared fixtures for the core suite. Network access is forbidden here."""

import socket

import pytest

from xteink.core import DeviceService, KeyService, LibraryService, Store


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Fail the test if anything in the core suite opens a socket."""
    opened = []

    def _boom(*args, **kwargs):
        opened.append(args)
        raise AssertionError("network I/O attempted in xteink.core suite")

    monkeypatch.setattr(socket, "socket", _boom)
    monkeypatch.setattr(socket, "create_connection", _boom)
    yield opened
    assert opened == []


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "data")


@pytest.fixture
def library(store):
    return LibraryService(store)


@pytest.fixture
def devices(store):
    return DeviceService(store)


@pytest.fixture
def keys(store):
    return KeyService(store)
