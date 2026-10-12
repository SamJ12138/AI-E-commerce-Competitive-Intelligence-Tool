"""Batch 3: prices and discounts, loyalty, Google Analytics, payment methods, brand positioning."""

from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from modules.models import Platform
from modules.product_extractor import ProductExtractor, extract_products
from modules.promo_extractor import extract_promotions
from modules.trust_extractor import extract_trust_signals

STORES = Path(__file__).resolve().parent / "fixtures" / "stores"


def _soup(rel):
    html = (STORES / rel).read_text(encoding="utf-8")
    return BeautifulSoup(html, "lxml"), html


def _page(body, head=""):
    html = f"<html><head>{head}</head><body>{body}</body></html>"
    return BeautifulSoup(html, "lxml"), html


def _prices(rel, platform, page_type="collection"):
    soup, _ = _soup(rel)
    return {p.title: (p.price.current_price, p.price.compare_at_price, p.price.is_on_sale)
            for p in extract_products(soup, "http://shop.test/x", platform, page_type) if p.price}


# --- prices --------------------------------------------------------------------------------

def test_dawn_cards_struck_price_is_compare_at():
    got = _prices("shopify_basic/collections/all.html", Platform.SHOPIFY)
    assert got["Classic Tee"] == (24.0, None, False)
    assert got["Everyday Hoodie"] == (39.0, 49.0, True)


def test_woocommerce_cards_del_is_compare_at_ins_is_current():
    got = _prices("woocommerce_promo/shop.html", Platform.WOOCOMMERCE)
    assert got["Linen Shirt"] == (48.0, 60.0, True)
    assert got["Canvas Tote"] == (28.0, 35.0, True)


def test_woocommerce_product_page_price():
    got = _prices("woocommerce_promo/product/linen-shirt.html", Platform.WOOCOMMERCE, "product")
    assert got["Linen Shirt"] == (48.0, 60.0, True)


@pytest.mark.parametrize("price,compare,expected", [
    ("39.00", "49.00", (39.0, 49.0, True)),      # /products.json: strings in dollars
    ("24.00", None, (24.0, None, False)),
    (3900, 4900, (39.0, 49.0, True)),            # theme product JSON: integer cents
    (99, None, (0.99, None, False)),
])
def test_shopify_json_prices(price, compare, expected):
    p = ProductExtractor(Platform.SHOPIFY)._parse_shopify_product(
        {"title": "Hoodie", "handle": "hoodie", "variants": [{"price": price, "compare_at_price": compare}]},
        "http://shop.test")
    assert (p.price.current_price, p.price.compare_at_price, p.price.is_on_sale) == expected


@pytest.mark.parametrize("store,expected", [
    ("shopify_basic", (24.0, 39.0, 31.5, True)),
    ("woocommerce_promo", (28.0, 48.0, 38.0, True)),
])
def test_site_price_stats_and_discounts(analyzed, store, expected):
    intel = analyzed[store]
    assert (intel.price_min, intel.price_max, intel.price_median, intel.has_discounts) == expected


# --- loyalty -------------------------------------------------------------------------------

@pytest.mark.parametrize("body", [
    '<div class="yotpo yotpo-main-widget" data-product-id="1"></div>'
    '<script src="https://staticw2.yotpo.com/abc/widget.js"></script>',
    '<div class="jdgm-widget jdgm-review-widget">Customer Reviews</div><script>window.jdgmSettings={}</script>',
    '<form><label><input type="checkbox"> Remember me</label></form><p>Our membership of the guild</p>',
])
def test_review_widgets_and_stray_words_are_not_loyalty(body):
    soup, html = _page(body)
    assert extract_promotions(soup, html)["has_loyalty_program"] is False


@pytest.mark.parametrize("body", [
    '<section><h2>Harbor Rewards</h2><p>Join our loyalty program and earn 1 point for every $1.</p></section>',
    '<script src="https://cdn.sweettooth.io/assets/storefront.js"></script><div id="smile-ui-container"></div>'
    '<script src="https://js.smile.io/v1/smile-shopify.js"></script>',
])
def test_loyalty_programs_are_detected(body):
    soup, html = _page(body)
    assert extract_promotions(soup, html)["has_loyalty_program"] is True


def test_fixture_loyalty():
    for rel, expected in (("shopify_basic/index.html", False), ("woocommerce_promo/index.html", True)):
        soup, html = _soup(rel)
        assert extract_promotions(soup, html)["has_loyalty_program"] is expected, rel


# --- Google Analytics ----------------------------------------------------------------------

def _ga(body, head=""):
    soup, html = _page(body, head)
    return next(p for p in extract_promotions(soup, html)["pixels"] if p.name == "Google Analytics")


@pytest.mark.parametrize("body", [
    '<a class="header__heading-link" href="/">Shop</a><div class="shipping-bar img-wrapper">x</div>',
    '<p>Use code G-SUMMER24 at checkout</p>',
    '<script>var cfg = {"theme": "g-dark"};</script>',
])
def test_ga_not_detected_from_class_names_or_text(body):
    assert _ga(body).detected is False


@pytest.mark.parametrize("script", [
    "window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}gtag('config', 'G-7QF2KX9M3B');",
    "ga('create', 'UA-1234567-1', 'auto');",
])
def test_ga_detected_in_scripts_with_id(script):
    pixel = _ga(f"<script>{script}</script>")
    assert pixel.detected is True
    assert pixel.identifier == ("G-7QF2KX9M3B" if "G-" in script else "UA-1234567-1")


def test_ga_detected_from_gtag_loader_src():
    pixel = _ga('<script async src="https://www.googletagmanager.com/gtag/js?id=G-ABCDE12345"></script>')
    assert pixel.detected is True and pixel.identifier == "G-ABCDE12345"


def test_fixture_pixels():
    soup, html = _soup("shopify_basic/index.html")
    assert not [p.name for p in extract_promotions(soup, html)["pixels"] if p.detected]
    soup, html = _soup("woocommerce_promo/index.html")
    ga = [p for p in extract_promotions(soup, html)["pixels"] if p.detected]
    assert [(p.name, p.identifier) for p in ga] == [("Google Analytics", "G-7QF2KX9M3B")]


# --- payment methods -----------------------------------------------------------------------

def _payments(body):
    soup, html = _page(body)
    return sorted(extract_trust_signals(soup, html)["payment_methods"])


def test_fixture_card_brands():
    soup, html = _soup("shopify_basic/index.html")
    assert sorted(extract_trust_signals(soup, html)["payment_methods"]) == ["PayPal", "Visa"]
    soup, html = _soup("woocommerce_promo/index.html")
    assert sorted(extract_trust_signals(soup, html)["payment_methods"]) == ["Mastercard", "PayPal", "Visa"]


def test_brands_named_in_text():
    assert _payments("<p>We accept Visa, Mastercard and American Express.</p>") == \
        ["American Express", "Mastercard", "Visa"]


def test_generic_credit_card_only_without_a_brand():
    assert _payments("<p>We accept all major credit cards.</p>") == ["Credit Card"]


def test_substrings_are_not_payment_methods():
    assert _payments("<p>Discover our new collection. A daily affirmation. Visas for travel.</p>") == []


# --- brand positioning ---------------------------------------------------------------------

def test_positioning_is_the_meta_description_verbatim():
    import main
    soup, html = _soup("shopify_basic/index.html")
    info = main.extract_brand_info(soup, html)
    assert info.positioning == "Northfield Goods makes simple cotton basics, cut and sewn in small batches."
    assert info.positioning_source == "meta description"


def test_positioning_falls_back_to_title_tagline_then_null():
    import main
    soup, html = _page("<h1>Shop</h1>", "<title>Acme &#8211; Tools for small workshops</title>")
    info = main.extract_brand_info(soup, html)
    assert (info.positioning, info.positioning_source) == ("Tools for small workshops", "title")
    soup, html = _page("<div>stylesheet shipping women</div>", "<title>Acme</title>")
    info = main.extract_brand_info(soup, html)
    assert info.positioning is None and info.positioning_source is None


def test_fixture_positioning_is_quoted_from_the_page(analyzed):
    for store, intel in analyzed.items():
        page = (STORES / store / "index.html").read_text(encoding="utf-8")
        assert intel.brand_positioning and intel.brand_positioning in page, store


# --- return window wording -----------------------------------------------------------------

def test_return_policy_lasts_n_days(analyzed):
    assert analyzed["woocommerce_promo"].return_policy.return_days == 14
    assert analyzed["woocommerce_promo"].return_policy.free_returns is False
