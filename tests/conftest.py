"""Shared pytest fixtures: the local fixture stores on 127.0.0.1."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent / "fixtures" / "stores"))

from server import STORE_NAMES, StoreServer  # noqa: E402


def pytest_configure(config):
    config.addinivalue_line("markers", "live: calls a real paid API; skips unless its key is set")


@pytest.fixture(scope="session")
def fixture_stores():
    """Start every fixture store once per session; yields {name: StoreServer}."""
    servers = {name: StoreServer(name).start() for name in STORE_NAMES}
    yield servers
    for srv in servers.values():
        srv.stop()


def analyze_store(store, **config):
    """Run main.analyze_site against one fixture store in-process (no rate-limit delay)."""
    import main
    from modules.http_client import HttpClient
    from modules.models import Config
    from modules.robots_checker import RobotsChecker
    with StoreServer(store) as srv:
        cfg = Config(rate_limit_delay=0, timeout=10, **config)
        client = HttpClient(cfg)
        try:
            intel = main.analyze_site(srv.base_url, client, RobotsChecker(cfg), cfg)
        finally:
            client.close()
        return intel, srv.request_log()


@pytest.fixture(scope="session")
def analyzed():
    """{store: SiteIntelligence} for the two stores that answer."""
    return {store: analyze_store(store)[0] for store in ("shopify_basic", "woocommerce_promo")}
