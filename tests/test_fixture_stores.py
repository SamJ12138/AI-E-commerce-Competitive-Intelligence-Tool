"""Checks on the fixture stores themselves: they serve what fixtures.json says."""

import re
import time

import pytest
import requests

from server import STORES_DIR, StoreServer, load_ground_truth

OK_STORES = ("shopify_basic", "woocommerce_promo")


def _page_paths(truth):
    pages = truth["pages"]
    paths = [pages["home"], pages["collection"], pages["shipping_policy"],
             pages["refund_policy"], pages["robots"]]
    return paths + list(pages["products"])


@pytest.mark.parametrize("store", OK_STORES)
def test_every_listed_page_is_served(fixture_stores, store):
    srv = fixture_stores[store]
    for path in _page_paths(srv.truth):
        resp = requests.get(srv.base_url + path, timeout=5)
        assert resp.status_code == 200, path


@pytest.mark.parametrize("store", OK_STORES)
def test_not_served_paths_404(fixture_stores, store):
    srv = fixture_stores[store]
    for path in srv.truth["not_served"] + ["/fixtures.json", "/no-such-page"]:
        assert requests.get(srv.base_url + path, timeout=5).status_code == 404, path


@pytest.mark.parametrize("store", OK_STORES)
def test_product_pages_show_ground_truth_prices(fixture_stores, store):
    srv = fixture_stores[store]
    for product in srv.truth["products"]:
        html = requests.get(srv.base_url + product["url"], timeout=5).text
        assert product["title"] in html
        assert f"{product['price']:.2f}" in html
        if product["compare_at_price"] is not None:
            assert f"{product['compare_at_price']:.2f}" in html


@pytest.mark.parametrize("store", OK_STORES)
def test_expected_price_stats_match_products(store):
    truth = load_ground_truth(store)
    prices = sorted(p["price"] for p in truth["products"])
    exp = truth["expected"]
    assert exp["price_min"] == prices[0]
    assert exp["price_max"] == prices[-1]
    assert exp["has_discounts"] == any(p["on_sale"] for p in truth["products"])


@pytest.mark.parametrize("store", OK_STORES)
def test_pages_never_trigger_external_fetches(store):
    """Fixtures must not make a browser fetch anything off 127.0.0.1."""
    auto_fetch = re.compile(r'<(?:script|img|link|iframe)\b[^>]*\b(?:src|href)="(https?:)?//', re.I)
    for page in (STORES_DIR / store).rglob("*.html"):
        assert not auto_fetch.search(page.read_text(encoding="utf-8")), page


def test_blocked_store_answers_403_everywhere(fixture_stores):
    srv = fixture_stores["blocked"]
    for path in ("/", "/robots.txt", "/collections/all", "/products/anything"):
        resp = requests.get(srv.base_url + path, timeout=5)
        assert resp.status_code == 403, path
        assert resp.headers["Server"] == "cloudflare"
        assert resp.headers["cf-mitigated"] == "challenge"
        assert "Just a moment..." in resp.text


def test_requests_are_recorded(fixture_stores):
    srv = fixture_stores["shopify_basic"]
    before = len(srv.request_log())
    requests.get(srv.base_url + "/robots.txt", timeout=5)
    log = srv.request_log()
    assert len(log) == before + 1
    assert log[-1]["path"] == "/robots.txt" and log[-1]["status"] == 200


def test_a_request_is_recorded_before_its_response_is_sent(monkeypatch):
    # The client can return before the server thread runs again; a request recorded after the
    # body was written could be missing from request_log() (seen as a flaky test_page_loop).
    record = StoreServer._record

    def slow_record(self, *args):
        time.sleep(0.3)
        record(self, *args)
    monkeypatch.setattr(StoreServer, "_record", slow_record)
    with StoreServer("shopify_basic") as srv:
        requests.get(srv.base_url + "/robots.txt", timeout=5)
        assert [r["path"] for r in srv.request_log()] == ["/robots.txt"]
