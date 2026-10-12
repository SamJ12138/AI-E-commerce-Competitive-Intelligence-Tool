"""Every page body the tool reads is one a server sent: HttpClient never makes one up."""

import ast
import itertools
from pathlib import Path

import pytest

import modules.http_client as http_client
from modules.http_client import HttpClient
from modules.models import Config

ROOT = Path(__file__).resolve().parent.parent

# Formerly special-cased (lululemon, nike, adidas) and ordinary hosts.
URLS = ["https://www.nike.com/", "https://shop.lululemon.com/", "https://www.adidas.com/us",
        "https://www.lululemon.com/en-us/", "https://store.example.test/"]

# What one transport can answer: (html, status, error). A body only ever comes with a status
# the transport itself received.
OUTCOMES = {
    "ok": ("<p>{branch} body</p>", 200, None),
    "403": (None, 403, "blocked (403)"),
    "403-with-body": ("<p>{branch} challenge</p>", 403, "blocked (403)"),
    "404": (None, 404, "Page not found (404)"),
    "no-response": (None, 0, "connection refused"),
}


def _transport(branch, outcome, sent):
    html, status, error = OUTCOMES[outcome]

    def fetch(url):
        body = html.format(branch=branch) if html else None
        if body:
            sent.add(body)
        return body, status, {"Server": branch}, error
    return fetch


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(http_client, "CLOUDSCRAPER_AVAILABLE", True)
    c = HttpClient(Config(rate_limit_delay=0))
    c.cloudscraper_session = object()   # never used: the branch below is replaced
    yield c
    c.close()


@pytest.mark.parametrize("render_js", [False, True])
def test_fetch_returns_only_bodies_a_transport_received(client, render_js):
    combos = itertools.product(OUTCOMES, repeat=3)
    for url, (first, honest, second) in itertools.product(URLS, combos):
        sent = set()
        first_branch = "browser" if render_js else "requests"
        client._fetch_with_playwright = _transport("browser", first, sent)
        client._fetch_with_requests = _transport("requests", first, sent)
        client._fetch_with_honest_ua = _transport("honest-ua", honest, sent)
        client._fetch_with_cloudscraper = _transport("cloudscraper", second, sent)

        html, status, headers, error = client.fetch(url, render_js=render_js)

        case = f"{url} {first_branch}={first} honest-ua={honest} cloudscraper={second}"
        assert html is None or html in sent, case
        tried = [a["branch"] for a in client.last_chain]
        assert set(tried) <= {first_branch, "honest-ua", "cloudscraper"}, case
        assert render_js is False or "honest-ua" not in tried, case
        # The status returned is the status of the last branch tried, never one the tool chose.
        assert status == client.last_chain[-1]["status"], case
        if status != 200:
            assert error, case


def test_protected_domains_go_through_the_normal_chain(client):
    sent = set()
    client._fetch_with_playwright = _transport("browser", "403", sent)
    client._fetch_with_cloudscraper = _transport("cloudscraper", "403", sent)
    html, status, headers, error = client.fetch("https://www.nike.com/", render_js=True)
    assert (html, status) == (None, 403) and error
    assert [(a["branch"], a["status"]) for a in client.last_chain] == [("browser", 403), ("cloudscraper", 403)]
    assert "X-Bot-Protection" not in headers


def test_a_formerly_protected_site_ends_blocked_on_what_it_returned(client):
    import main

    class AllowAll:
        def is_allowed(self, url):
            return True

        def get_sitemaps(self, url):
            return []

        def get_crawl_delay(self, url):
            return None

    client.config.render_js = True
    sent = set()
    client._fetch_with_playwright = _transport("browser", "403-with-body", sent)
    client._fetch_with_cloudscraper = _transport("cloudscraper", "403", sent)
    intel = main.analyze_site("https://www.nike.com", client, AllowAll(), Config(rate_limit_delay=0, render_js=True))
    assert intel.status == "blocked"
    assert intel.fetch_attempts == ["browser 403", "cloudscraper 403"]
    assert intel.platform is None and intel.has_popup is None


def _string_constants(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)]


def test_no_page_generator_in_the_source():
    assert not hasattr(HttpClient, "PROTECTED_SITES")
    assert not hasattr(HttpClient, "_fetch_protected_site")
    for path in [ROOT / "main.py", *sorted((ROOT / "modules").glob("*.py"))]:
        for s in _string_constants(path):
            low = s.lower()
            assert "<html" not in low and "<!doctype" not in low and "<body" not in low, (path.name, s[:80])
