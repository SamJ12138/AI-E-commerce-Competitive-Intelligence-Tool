"""Phase 3 Batch 2: one homepage fetch, /products.json only when linked, announcement bar."""

from urllib.parse import urlsplit

import pytest
from bs4 import BeautifulSoup

import main
from modules.promo_extractor import PromoExtractor
from tests.conftest import analyze_store
from server import load_ground_truth


@pytest.fixture(scope="module")
def runs():
    return {store: analyze_store(store) for store in ("shopify_basic", "woocommerce_promo")}


def _paths(log):
    return [(urlsplit(r["path"]).path, r["status"]) for r in log]


@pytest.mark.parametrize("store", ["shopify_basic", "woocommerce_promo"])
def test_homepage_is_fetched_once_and_its_headers_are_read(runs, store):
    intel, log = runs[store]
    assert [p for p, _ in _paths(log)].count("/") == 1
    if store == "shopify_basic":
        assert "header:x-shopify-stage" in intel.platform_signals


def test_products_json_not_requested_when_the_homepage_does_not_link_it(runs):
    intel, log = runs["shopify_basic"]
    paths = _paths(log)
    assert "/products.json" not in [p for p, _ in paths]
    assert [s for _, s in paths if s == 404] == []
    assert intel.price_max == 39.0          # prices still come from the HTML pages


BASE = "https://shop.example.test/"


@pytest.mark.parametrize("html, expected", [
    ('<a href="/products/tee">Tee</a><a href="/collections/all">All</a>', False),
    ('<script>Shopify.theme = {"name": "Dawn"};</script>', False),
    ('<a href="/products.json">feed</a>', True),
    ('<link rel="alternate" type="application/json" href="https://shop.example.test/products.json">', True),
    ('<div data-product-json="/products/tee.js"></div>', True),
    ('<link rel="alternate" type="application/json+oembed" href="/products/tee.oembed">', True),
    ('<a href="/collections/sale/products.json">sale</a>', True),
    ('<a href="https://other.example/products.json">elsewhere</a>', False),
    ('<a href="/products/tee.jsonl">x</a>', False),
])
def test_products_json_suggested_only_by_a_link_to_a_json_product_endpoint(html, expected):
    assert main.products_json_linked(BeautifulSoup(html, "html.parser"), BASE) is expected


def test_announcement_bars_match_the_ground_truth(runs):
    for store in ("shopify_basic", "woocommerce_promo"):
        expected = load_ground_truth(store)["expected"]["announcement_bar"]
        assert runs[store][0].announcement_bar_text == expected, store


def test_woocommerce_store_notice_is_the_announcement_without_its_dismiss_link():
    html = ('<body><p class="woocommerce-store-notice demo_store" style="display:none;">'
            'Spring sale: 10% off. <a href="#" class="woocommerce-store-notice__dismiss-link">Dismiss</a></p>'
            '<header><div class="col-full"><nav><ul><li><a href="/shop/">Shop</a></li>'
            '<li><a href="/shipping/">Shipping</a></li></ul></nav></div></header></body>')
    text = PromoExtractor()._extract_announcement_bar(BeautifulSoup(html, "html.parser"))
    assert text == "Spring sale: 10% off."


def test_header_navigation_is_not_an_announcement():
    html = ('<body><header><div class="col-full"><a href="/">Harbor Supply Co.</a>'
            '<nav><ul><li><a href="/">Home</a></li><li><a href="/shop/">Shop</a></li>'
            '<li><a href="/shipping-policy/">Shipping</a></li></ul></nav></div></header></body>')
    assert PromoExtractor()._extract_announcement_bar(BeautifulSoup(html, "html.parser")) == ""


def test_a_promo_line_at_the_top_of_the_header_still_counts():
    html = ('<body><header><div class="top-strip">Free shipping on orders over $40</div>'
            '<nav><a href="/shop">Shop</a></nav></header></body>')
    text = PromoExtractor()._extract_announcement_bar(BeautifulSoup(html, "html.parser"))
    assert text == "Free shipping on orders over $40"
