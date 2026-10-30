"""Shared fixtures: enforce the offline contract for every unit test.

Every test in this directory must run with no API key and no network.
META_API_KEY is scrubbed (tests that exec scripts requiring the variable
set an explicit fake) and socket connects raise.
"""

import socket

import pytest


@pytest.fixture(autouse=True)
def _no_real_key(monkeypatch):
    monkeypatch.delenv("META_API_KEY", raising=False)


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def _blocked(*args, **kwargs):
        raise AssertionError("unit tests must not touch the network")

    monkeypatch.setattr(socket, "create_connection", _blocked)
    monkeypatch.setattr(socket.socket, "connect", _blocked)
