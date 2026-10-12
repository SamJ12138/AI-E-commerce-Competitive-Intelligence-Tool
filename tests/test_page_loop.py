"""max_products caps the products, not the pages: policy pages queued after a big collection are
still fetched (Phase 3 Batch 4; allbirds, rastaclat and deathwishcoffee stopped after one collection)."""

from urllib.parse import urlsplit

from tests.conftest import analyze_store


def _paths(log):
    return [urlsplit(r["path"]).path.rstrip("/") or "/" for r in log]


def test_policies_are_read_after_max_products_is_reached():
    # shopify_basic: /collections/all has 2 product cards and comes before the two policy pages.
    intel, log = analyze_store("shopify_basic", max_products=1)
    paths = _paths(log)
    assert "/policies/shipping-policy" in paths and "/policies/refund-policy" in paths
    assert intel.return_policy is not None and intel.return_policy.return_days == 30
    assert intel.shipping_policy is not None and intel.shipping_policy.free_shipping_threshold == 50.0
    assert len(intel.all_products) == 1


def test_no_more_product_pages_once_max_products_is_reached():
    intel, log = analyze_store("shopify_basic", max_products=1)
    assert not [p for p in _paths(log) if p.startswith("/products/")]


def test_woocommerce_policies_after_max_products():
    intel, log = analyze_store("woocommerce_promo", max_products=1)
    assert intel.return_policy is not None and intel.return_policy.return_days == 14
    assert intel.return_policy.free_returns is False


# A Shopify homepage whose mega-menu links 25 collections before the footer's policy links
# (allbirds: 37 links, rastaclat: 46; the page list was 19 collections and nothing else).
MENU = [(f"/collections/c{i}", f"Collection {i}") for i in range(25)]
PRODUCTS = [(f"/products/p{i}", f"Product {i}") for i in range(8)]
FOOTER = [("/pages/return-policy", "Return Policy"), ("/policies/shipping-policy", "Shipping")]


def test_policy_pages_get_a_place_in_max_pages():
    from modules.models import Platform
    from tests.test_discovery import _discover
    pages, _ = _discover(MENU + PRODUCTS + FOOTER, Platform.SHOPIFY, max_pages=20)
    assert len(pages) == 19
    assert "/pages/return-policy" in pages and "/policies/shipping-policy" in pages
    assert any(p.startswith("/products/") for p in pages)
    assert sum(p.startswith("/collections/") for p in pages) >= 2
