"""--render-js: an HTTP error the browser receives is an error, not page content (Phase 5 Batch 2,
found while reading the browser path for the first real --render-js run). The browser branch
returned the body of a 403 challenge or a 404 page with no error, so without the cloudscraper
fallback (real-site runs switch it off) a challenge page was parsed as the store."""

import pytest

import modules.http_client as http_client
from modules.http_client import HttpClient
from modules.models import Config

CHALLENGE = "<html><head><title>Just a moment...</title></head><body>Checking your browser</body></html>"


class FakeResponse:
    def __init__(self, status):
        self.status = status
        self.headers = {"content-type": "text/html"}


class FakePage:
    def __init__(self, status, body):
        self.status, self.body = status, body

    def goto(self, url, timeout=None, wait_until=None):
        return FakeResponse(self.status)

    def wait_for_selector(self, selector, timeout=None):
        pass

    def wait_for_timeout(self, ms):
        pass

    def content(self):
        return self.body

    def close(self):
        pass


class FakeContext:
    def __init__(self, status, body):
        self.status, self.body = status, body

    def new_page(self):
        return FakePage(self.status, self.body)


def _client(monkeypatch, status, body):
    monkeypatch.setattr(http_client, "CLOUDSCRAPER_AVAILABLE", False)
    monkeypatch.setattr(HttpClient, "_init_playwright", lambda self: None)
    client = HttpClient(Config(rate_limit_delay=0, render_js=True))
    client._context = FakeContext(status, body)
    return client


@pytest.mark.parametrize("status, kind", [(403, "403"), (404, "404"), (429, "429"), (503, "503")])
def test_http_error_in_the_browser_is_an_error(monkeypatch, status, kind):
    client = _client(monkeypatch, status, CHALLENGE)
    html, got, _headers, error = client.fetch("https://shop.example/")
    assert html is None and got == status
    assert error and kind in error
    assert client.last_chain[-1]["branch"] == "browser"


def test_a_200_page_is_content(monkeypatch):
    client = _client(monkeypatch, 200, "<html><body><h1>Store</h1></body></html>")
    html, status, _headers, error = client.fetch("https://shop.example/")
    assert status == 200 and error is None and "<h1>Store</h1>" in html
