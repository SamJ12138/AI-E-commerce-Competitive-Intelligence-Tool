"""Honest-UA retry: on a 403/429 to the browser-like headers, the same URL is asked once more
with a User-Agent that names the tool and its repository, before the other fallbacks."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

import main
import modules.http_client as http_client
from modules import obs
from modules.http_client import HttpClient
from modules.models import Config
from modules.robots_checker import RobotsChecker
from server import StoreServer

REPO_URL = "https://github.com/SamJ12138/AI-E-commerce-Competitive-Intelligence-Tool"


def _events(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


@pytest.fixture(scope="module")
def ua_filtered(tmp_path_factory):
    """shopify_basic behind a server that refuses browser-like requests (barefootbuttons' nginx)."""
    log_dir = tmp_path_factory.mktemp("obs")
    run_id = obs.init_run(log_dir=str(log_dir), run_id="ua")
    try:
        with StoreServer("shopify_basic", refuse_browser_ua=True) as srv:
            cfg = Config(rate_limit_delay=0, timeout=10)
            client = HttpClient(cfg)
            try:
                intel = main.analyze_site(srv.base_url, client, RobotsChecker(cfg), cfg)
            finally:
                client.close()
            requests_seen = srv.request_log()
            base = srv.base_url
    finally:
        obs.close_run()
    return intel, requests_seen, _events(log_dir / f"run_{run_id}.jsonl"), base


def test_store_refusing_browser_headers_ends_ok(ua_filtered):
    intel, _, _, _ = ua_filtered
    assert intel.status == "ok"
    assert intel.platform.value == "Shopify"
    assert intel.price_max == 39 and intel.shipping_policy.free_shipping_threshold == 50


def test_same_url_asked_once_more_with_an_honest_user_agent(ua_filtered):
    _, seen, _, _ = ua_filtered
    home = [r for r in seen if r["path"] == "/"]
    assert [r["status"] for r in home] == [403, 200]
    assert "Mozilla/" in home[0]["user_agent"]
    honest = home[1]["user_agent"]
    assert REPO_URL in honest and "Mozilla" not in honest and "Chrome" not in honest
    # Every page: the browser-like request first, then exactly one honest retry.
    for path in {r["path"] for r in seen}:
        assert [r["status"] for r in seen if r["path"] == path] == [403, 200], path


def test_robots_txt_read_with_the_honest_user_agent(ua_filtered):
    _, seen, events, _ = ua_filtered
    assert [r["status"] for r in seen if r["path"] == "/robots.txt"] == [403, 200]
    # The rules were read (Shopify's robots.txt disallows /cart), not taken as "no robots.txt".
    assert not [r for r in seen if r["path"].startswith("/cart")]


def test_obs_log_records_which_identity_got_through(ua_filtered):
    _, _, events, base = ua_filtered
    home = [e for e in events if e["stage"] == "fetch" and e["context"].get("url") in (base, base + "/")
            and e["event"] == "success"]
    assert home, "no successful fetch event for the homepage"
    ctx = home[0]["context"]
    assert ctx["served_by"] == "honest-ua"
    assert ctx["identity"] == "honest User-Agent"
    assert [(c["branch"], c["status"], c["identity"]) for c in ctx["chain"]] == [
        ("requests", 403, "browser-like headers"), ("honest-ua", 200, "honest User-Agent")]


# --- the chain with stubbed transports ---------------------------------------------------------

def _stub(branch, status, calls):
    def fetch(url):
        calls.append(branch)
        if status == 200:
            return f"<p>{branch}</p>", 200, {}, None
        return None, status, {}, f"{branch} {status}"
    return fetch


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(http_client, "CLOUDSCRAPER_AVAILABLE", True)
    c = HttpClient(Config(rate_limit_delay=0))
    c.cloudscraper_session = object()
    yield c
    c.close()


@pytest.mark.parametrize("first,honest,expected", [
    (200, None, ["requests"]),                                  # served: no retry
    (404, None, ["requests"]),                                  # not a refusal
    (403, 200, ["requests", "honest-ua"]),
    (429, 200, ["requests", "honest-ua"]),
    (403, 403, ["requests", "honest-ua", "cloudscraper"]),      # then the existing fallback
    (429, 429, ["requests", "honest-ua"]),                      # cloudscraper only follows a 403
    (429, 403, ["requests", "honest-ua", "cloudscraper"]),
])
def test_default_chain(client, first, honest, expected):
    calls = []
    client._fetch_with_requests = _stub("requests", first, calls)
    client._fetch_with_honest_ua = _stub("honest-ua", honest, calls)
    client._fetch_with_cloudscraper = _stub("cloudscraper", 403, calls)
    client.fetch("https://store.example.test/")
    assert calls == expected
    assert [a["branch"] for a in client.last_chain] == expected


def test_render_js_chain_unchanged(client):
    calls = []
    client._fetch_with_playwright = _stub("browser", 403, calls)
    client._fetch_with_honest_ua = _stub("honest-ua", 200, calls)
    client._fetch_with_cloudscraper = _stub("cloudscraper", 403, calls)
    client.fetch("https://store.example.test/", render_js=True)
    assert calls == ["browser", "cloudscraper"]


class _TooMany(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(429)
        self.send_header("Retry-After", "0")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *args):
        pass


def test_a_429_is_returned_as_429_not_as_a_connection_error(monkeypatch):
    # urllib3 retries 429 itself; the last 429 used to surface as a RetryError (status 0, i.e.
    # "no HTTP answer"), so neither the honest retry nor the blocked status could see it.
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _TooMany)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        c = HttpClient(Config(rate_limit_delay=0, timeout=5))
        for adapter in c.session.adapters.values():
            adapter.max_retries.backoff_factor = 0
        html, status, headers, error = c._fetch_with_requests(f"http://127.0.0.1:{srv.server_address[1]}/")
        c.close()
    finally:
        srv.shutdown()
        srv.server_close()
    assert (html, status) == (None, 429) and "429" in error
