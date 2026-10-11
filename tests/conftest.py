"""Shared pytest fixtures: the local fixture stores on 127.0.0.1."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent / "fixtures" / "stores"))

from server import STORE_NAMES, StoreServer  # noqa: E402


@pytest.fixture(scope="session")
def fixture_stores():
    """Start every fixture store once per session; yields {name: StoreServer}."""
    servers = {name: StoreServer(name).start() for name in STORE_NAMES}
    yield servers
    for srv in servers.values():
        srv.stop()
