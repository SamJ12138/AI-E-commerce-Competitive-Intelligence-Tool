"""Dead extraction code removed (Phase 5 Batch 4).

policy_evidence.py: only modules/__init__.py re-exported it; nothing used it. price_extractor.py:
a seven-method fallback on the homepage HTML, run only when no product had a price. In every
real-store run log kept from Phases 3-5 only the last method ever produced the range (prices
written in the homepage text); that path now lives in product_extractor.homepage_price_fallback
and the rest is gone."""

import importlib.util

import pytest

import modules
from modules.product_extractor import homepage_price_fallback
from tests.page_server import analyze_pages, shopify_page


@pytest.mark.parametrize("name", ["modules.policy_evidence", "modules.price_extractor"])
def test_module_is_gone(name):
    assert importlib.util.find_spec(name) is None


def test_package_no_longer_exports_them():
    for name in ("PolicyEvidenceLadder", "PolicyEvidence", "EvidenceLevel", "create_blocked_policy_note",
                 "extract_prices_from_js", "extract_price_stats_from_html"):
        assert name not in modules.__all__ and not hasattr(modules, name)


@pytest.mark.parametrize("html, expected", [
    ("<p>Tee $24.00</p><p>Hoodie $39.00</p><p>Cap $31.50</p>", (24.0, 39.0, 31.5, "USD")),
    ("<p>Mug £12.50</p><p>Tin £8</p>", (8.0, 12.5, 10.25, "GBP")),
    ('<script>Shopify.currency = {"active":"CAD","rate":"1.0"};</script><p>$20</p><p>$30</p>',
     (20.0, 30.0, 25.0, "CAD")),
    ("<p>Shipping $4.99</p><p>Gift cards up to $20000</p>", (None, None, None, "USD")),  # outside 5..10000
    ("<p>No prices here</p>", (None, None, None, "USD")),
])
def test_homepage_price_fallback(html, expected):
    assert homepage_price_fallback(html) == expected


# A store whose product pages carry no price (none visible, none in structured data): the price
# range comes from the amounts written on the homepage.
PAGES = {
    "/": shopify_page('<main><h1>Field Supply</h1><p>Canvas Tote - $28.00</p><p>Linen Shirt - $48.00</p>'
                      '<a href="/products/canvas-tote">Canvas Tote</a>'
                      '<a href="/products/linen-shirt">Linen Shirt</a></main>'),
    "/products/canvas-tote": shopify_page("<main><h1>Canvas Tote</h1><p>Sturdy cotton canvas.</p></main>"),
    "/products/linen-shirt": shopify_page("<main><h1>Linen Shirt</h1><p>Washed linen.</p></main>"),
}


def test_store_without_product_prices_uses_the_homepage_text():
    intel, log = analyze_pages(PAGES)
    assert "/products/canvas-tote" in log and "/products/linen-shirt" in log
    assert all(p.price is None for p in intel.all_products)
    assert (intel.price_min, intel.price_max, intel.price_median) == (28.0, 48.0, 38.0)
