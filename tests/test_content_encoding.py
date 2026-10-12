"""Compressed responses: the tool reads a page only after decoding it, and never asks for an
encoding it cannot decode (Phase 3 Batch 4; six real stores behind Cloudflare sent Brotli)."""

import gzip
import importlib.util
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from urllib3.util.request import ACCEPT_ENCODING

import main
from modules.http_client import HttpClient
from modules.models import Config, Platform
from modules.robots_checker import RobotsChecker

ENCODED = Path(__file__).resolve().parent / "fixtures" / "encoded"
PAGE = (ENCODED / "shopify_home.html").read_bytes()
PAGE_BR = (ENCODED / "shopify_home.html.br").read_bytes()   # brotli.compress(PAGE), made once
DECODABLE = {e.strip() for e in ACCEPT_ENCODING.split(",")} | {"identity"}


def _cloudflare_like(force_encoding=None):
    """Answers like a CDN: Brotli when the client offers br, else gzip, else identity."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/robots.txt":
                body, encoding = b"User-agent: *\nDisallow: /cart\n", None
            elif self.path == "/":
                offered = {e.split(";")[0].strip() for e in self.headers.get("Accept-Encoding", "").split(",")}
                if force_encoding:
                    body, encoding = PAGE, force_encoding
                elif "br" in offered:
                    body, encoding = PAGE_BR, "br"
                elif "gzip" in offered:
                    body, encoding = gzip.compress(PAGE), "gzip"
                else:
                    body, encoding = PAGE, None
            else:
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Server", "cloudflare")
            self.send_header("Content-Type", "text/html; charset=utf-8")
            if encoding:
                self.send_header("Content-Encoding", encoding)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


@pytest.fixture
def cdn():
    servers = []

    def start(force_encoding=None):
        srv, base = _cloudflare_like(force_encoding)
        servers.append(srv)
        return base
    yield start
    for srv in servers:
        srv.shutdown()
        srv.server_close()


def test_fixture_br_is_the_page():
    if importlib.util.find_spec("brotli") is None:
        pytest.skip("brotli not installed")
    import brotli
    assert brotli.decompress(PAGE_BR) == PAGE


def test_client_only_offers_encodings_it_can_decode():
    client = HttpClient(Config(rate_limit_delay=0))
    try:
        offered = {e.split(";")[0].strip() for e in client.session.headers["Accept-Encoding"].split(",")}
    finally:
        client.close()
    assert offered <= DECODABLE, f"offered {sorted(offered - DECODABLE)} but urllib3 here decodes {sorted(DECODABLE)}"


def test_cdn_page_is_decoded_before_it_is_read(cdn):
    base = cdn()
    cfg = Config(rate_limit_delay=0, timeout=10)
    client = HttpClient(cfg)
    try:
        intel = main.analyze_site(base, client, RobotsChecker(cfg), cfg)
    finally:
        client.close()
    assert intel.status == "ok"
    assert intel.platform == Platform.SHOPIFY
    assert intel.announcement_bar_text == "Free shipping on orders over $75"
    assert intel.has_email_capture is True
    assert intel.brand_positioning == "Lantern Row pours soy candles in small batches."


def test_a_body_the_client_cannot_decode_is_an_error_not_a_page(cdn):
    base = cdn(force_encoding="x-squash")
    client = HttpClient(Config(rate_limit_delay=0, timeout=10))
    try:
        html, status, headers, error = client.fetch(base + "/")
    finally:
        client.close()
    assert html is None
    assert "x-squash" in error


def test_brotli_is_advertised_only_with_a_decoder(monkeypatch):
    import modules.http_client as http_client
    monkeypatch.setattr(http_client, "BROTLI_AVAILABLE", False)
    client = HttpClient(Config(rate_limit_delay=0))
    try:
        assert "br" not in client.session.headers["Accept-Encoding"]
    finally:
        client.close()
