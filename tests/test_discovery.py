"""Batch 2: the homepage link crawl runs; guessed paths are platform-known and only fill gaps."""

from urllib.parse import urlsplit

import pytest
from bs4 import BeautifulSoup

from server import StoreServer, load_ground_truth
from modules.models import Config, Platform
from modules.page_discovery import discover_pages

BASE = "http://shop.test"


class FakeClient:
    """Answers 404 to everything and records what was asked."""

    def __init__(self):
        self.fetched = []

    def fetch(self, url, **kw):
        self.fetched.append(url)
        return None, 404, {}, "Not found (404)"

    def fetch_and_parse(self, url, **kw):
        self.fetched.append(url)
        return None, 404, "Not found (404)"


class AllowAll:
    def is_allowed(self, url):
        return True

    def get_sitemaps(self, url):
        return []


def _discover(links, platform, max_pages=20):
    html = "<html><body>" + "".join(f'<a href="{h}">{t}</a>' for h, t in links) + "</body></html>"
    client = FakeClient()
    pages = discover_pages(BASE, client, AllowAll(), Config(max_pages=max_pages, rate_limit_delay=0),
                           platform=platform, homepage_soup=BeautifulSoup(html, "html.parser"))
    return {urlsplit(u).path: t for u, t in pages}, [urlsplit(u).path for u in client.fetched]


def test_shopify_with_no_links_guesses_only_platform_paths():
    pages, _ = _discover([], Platform.SHOPIFY)
    assert pages == {"/collections/all": "collection", "/policies/shipping-policy": "policy",
                     "/policies/refund-policy": "policy"}


def test_woocommerce_with_no_links_guesses_only_platform_paths():
    pages, _ = _discover([], Platform.WOOCOMMERCE)
    assert pages == {"/shop": "collection", "/refund_returns": "policy"}


def test_unknown_platform_guesses_nothing():
    pages, fetched = _discover([], Platform.CUSTOM)
    assert pages == {} and fetched == []


def test_guessing_stops_for_page_types_the_crawl_found():
    pages, _ = _discover([("/collections/frontpage", "Shop"), ("/pages/returns", "Returns")], Platform.SHOPIFY)
    assert pages == {"/collections/frontpage": "collection", "/pages/returns": "policy",
                     "/policies/shipping-policy": "policy"}


def test_crawl_keeps_products_and_skips_cart_and_add_to_cart_links():
    pages, fetched = _discover([("/products/a", "A"), ("/product/b/", "B"), ("/cart", "Cart"),
                                ("?add-to-cart=12", "Add to cart"), ("/blog/news", "News"),
                                ("/shop/", "Shop"), ("/shipping-policy/", "Shipping"),
                                ("/refund_returns/", "Refunds")], Platform.WOOCOMMERCE)
    assert pages == {"/products/a": "product", "/product/b": "product", "/shop": "collection",
                     "/shipping-policy": "policy", "/refund_returns": "policy"}
    assert not any("add-to-cart" in u or u == "/cart" for u in fetched)


def test_max_pages_keeps_policies_ahead_of_the_product_list():
    links = [(f"/products/p{i}", f"P{i}") for i in range(30)] + [("/policies/refund-policy", "Refunds")]
    pages, _ = _discover(links, Platform.SHOPIFY, max_pages=5)
    assert len(pages) == 4  # the homepage counts as one of max_pages
    assert "/policies/refund-policy" in pages


def _paths_requested(store):
    import main
    from modules.http_client import HttpClient
    from modules.robots_checker import RobotsChecker
    with StoreServer(store) as srv:
        cfg = Config(rate_limit_delay=0, timeout=10)
        client = HttpClient(cfg)
        try:
            main.analyze_site(srv.base_url, client, RobotsChecker(cfg), cfg)
        finally:
            client.close()
        return [(urlsplit(r["path"]).path.rstrip("/") or "/", r["status"]) for r in srv.request_log()]


@pytest.mark.parametrize("store", ["shopify_basic", "woocommerce_promo"])
def test_every_fixture_page_is_fetched_with_few_404s(store):
    pages = load_ground_truth(store)["pages"]
    expected = {pages["home"], pages["collection"], pages["shipping_policy"], pages["refund_policy"],
                pages["robots"], *pages["products"]}
    requested = _paths_requested(store)
    missing = sorted(expected - {p for p, _ in requested})
    assert not missing, f"never fetched: {missing}"
    not_found = [p for p, s in requested if s == 404]
    assert len(not_found) <= 3, not_found
    assert not any(p in ("/cart", "/checkout", "/account") for p, _ in requested)
