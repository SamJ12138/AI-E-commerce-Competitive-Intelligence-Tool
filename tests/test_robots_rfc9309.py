"""robots.txt status handling per RFC 9309 section 2.3.1: 4xx = no rules, 5xx / no answer = disallow all."""

import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from modules.models import Config
from modules.robots_checker import RobotsChecker


class _Robots(BaseHTTPRequestHandler):
    status = 200
    body = b"User-agent: *\nDisallow: /private\n"
    delay = 0.0

    def do_GET(self):
        time.sleep(self.delay)
        self.send_response(self.status)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(self.body)

    def log_message(self, *args):
        pass


def _serve(status, delay=0.0):
    handler = type("H", (_Robots,), {"status": status, "delay": delay})
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


@pytest.fixture
def robots_at():
    servers = []

    def start(status, delay=0.0):
        srv, base = _serve(status, delay)
        servers.append(srv)
        return base
    yield start
    for srv in servers:
        srv.shutdown()
        srv.server_close()


def _checker(**kw):
    return RobotsChecker(Config(rate_limit_delay=0, **kw))


def test_200_rules_apply(robots_at):
    base = robots_at(200)
    rc = _checker()
    assert rc.is_allowed(base + "/")
    assert not rc.is_allowed(base + "/private/x")


@pytest.mark.parametrize("status", [404, 403])
def test_4xx_means_no_robots_txt_everything_allowed(robots_at, status):
    base = robots_at(status)
    rc = _checker()
    assert rc.is_allowed(base + "/")
    assert rc.is_allowed(base + "/private/x")
    assert rc.unreachable_reason(base + "/") is None


@pytest.mark.parametrize("status", [500, 503])
def test_5xx_means_disallow_all_for_the_run(robots_at, status):
    base = robots_at(status)
    rc = _checker()
    assert not rc.is_allowed(base + "/")
    assert not rc.is_allowed(base + "/products/x")
    assert rc.get_sitemaps(base + "/") == []
    assert str(status) in rc.unreachable_reason(base + "/")


def test_timeout_means_disallow_all(robots_at):
    base = robots_at(200, delay=3)
    rc = _checker(timeout=1)
    started = time.monotonic()
    assert not rc.is_allowed(base + "/")
    assert time.monotonic() - started < 2.5
    assert "timeout" in rc.unreachable_reason(base + "/").lower()


def test_no_response_means_disallow_all():
    with socket.socket() as s:     # a port nothing listens on
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    rc = _checker(timeout=2)
    assert not rc.is_allowed(f"http://127.0.0.1:{port}/")
    assert rc.unreachable_reason(f"http://127.0.0.1:{port}/")


def test_robots_fetched_once_per_run(robots_at):
    calls = []

    class Counting(_Robots):
        status = 503

        def do_GET(self):
            calls.append(self.path)
            super().do_GET()
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Counting)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        base = f"http://127.0.0.1:{srv.server_address[1]}"
        rc = _checker()
        for path in ("/", "/a", "/b"):
            assert not rc.is_allowed(base + path)
        assert calls == ["/robots.txt"]
    finally:
        srv.shutdown()
        srv.server_close()


def test_ignore_robots_still_wins(robots_at):
    base = robots_at(500)
    assert _checker(ignore_robots=True).is_allowed(base + "/")
