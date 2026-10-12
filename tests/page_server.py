"""Serve a dict of hand-written pages on 127.0.0.1 and run analyze_site on them (no network).

    PAGES = {"/": "<html>...", "/collections/a": "...", "/robots.txt": "User-agent: *\\n"}
    intel, log = analyze_pages(PAGES, max_products=20)

A path not in the dict answers 404. `log` is the list of paths requested, in order.
"""

import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict, List, Tuple
from urllib.parse import urlsplit

SHOPIFY_HEAD = ('<script>var Shopify = Shopify || {}; Shopify.shop = "fixture.myshopify.com"; '
                'Shopify.theme = {"name":"Dawn"};</script>')


def shopify_card(handle: str, title: str, price: float) -> str:
    """One Dawn-style product card (the markup of tests/fixtures/stores/shopify_basic, trimmed)."""
    return (f'<li class="grid__item"><div class="card-wrapper product-card-wrapper">'
            f'<h3 class="card__heading h5"><a href="/products/{handle}" class="full-unstyled-link">{title}</a></h3>'
            f'<div class="price"><span class="price-item price-item--regular">${price:.2f} USD</span></div>'
            f'</div></li>')


def shopify_page(body: str, title: str = "Fixture store") -> str:
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{title}</title>'
            f'{SHOPIFY_HEAD}</head><body>{body}</body></html>')


@contextmanager
def serve(pages: Dict[str, str]):
    """Yield (base_url, request_log) while the pages are served."""
    log: List[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = urlsplit(self.path).path
            log.append(path)
            body = pages.get(path.rstrip("/") or "/")
            self.send_response(200 if body is not None else 404)
            self.send_header("Content-Type", "text/plain" if path.endswith(".txt") else "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write((body if body is not None else "<html><body>Not found</body></html>").encode("utf-8"))

        def log_message(self, *args):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{srv.server_address[1]}", log
    finally:
        srv.shutdown()
        srv.server_close()


def analyze_pages(pages: Dict[str, str], **config) -> Tuple[object, List[str]]:
    """main.analyze_site on the served pages with no rate-limit delay; returns (intel, paths requested)."""
    import main
    from modules.http_client import HttpClient
    from modules.models import Config
    from modules.robots_checker import RobotsChecker

    pages = {"/robots.txt": "User-agent: *\nDisallow: /cart\n", **pages}
    with serve(pages) as (base, log):
        cfg = Config(rate_limit_delay=0, timeout=10, **config)
        client = HttpClient(cfg)
        try:
            intel = main.analyze_site(base, client, RobotsChecker(cfg), cfg)
        finally:
            client.close()
        return intel, list(log)
