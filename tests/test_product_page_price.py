"""A product page whose price is only in structured data (Phase 5 Batch 2; allbirds: the price is
drawn by JavaScript, the static HTML has it in a JSON-LD ProductGroup and in product meta tags)."""

from bs4 import BeautifulSoup

from modules.models import Platform
from modules.product_extractor import extract_products

URL = "https://shop.example/products/canvas-cruiser"
BODY = '<main><h1>Canvas Cruiser</h1><div class="pdp"><button>Add to cart</button></div></main>'
LD_GROUP = """<script type="application/ld+json">{"@context":"https://schema.org","@type":"ProductGroup",
"name":"Canvas Cruiser","offers":{"@type":"Offer","priceCurrency":"USD","price":75},
"hasVariant":[{"@type":"Product","sku":"CC-8"}]}</script>"""
LD_VARIANTS = """<script type="application/ld+json">{"@type":"ProductGroup","name":"Canvas Cruiser",
"hasVariant":[{"@type":"Product","offers":{"@type":"Offer","price":"82.00","priceCurrency":"USD"}}]}</script>"""
LD_AGGREGATE = """<script type="application/ld+json">[{"@type":"BreadcrumbList"},{"@type":"Product",
"name":"Canvas Cruiser","offers":{"@type":"AggregateOffer","lowPrice":"64.50","highPrice":"90","priceCurrency":"USD"}}]
</script>"""
META = '<meta property="product:price:amount" content="75.00"><meta property="product:price:currency" content="USD">'


def _price(head):
    html = f"<html><head>{head}</head><body>{BODY}</body></html>"
    [p] = extract_products(BeautifulSoup(html, "html.parser"), URL, Platform.SHOPIFY, "product")
    return p


def test_price_from_json_ld_product_group():
    p = _price(LD_GROUP)
    assert p.price is not None and p.price.current_price == 75.0 and p.price.currency == "USD"
    assert p.title == "Canvas Cruiser" and p.url == URL
    assert "JSON-LD" in p._obs["detail"]


def test_price_from_the_first_variant_offer():
    assert _price(LD_VARIANTS).price.current_price == 82.0


def test_price_from_an_aggregate_offer_is_the_low_price():
    assert _price(LD_AGGREGATE).price.current_price == 64.5


def test_price_from_product_meta():
    p = _price(META)
    assert p.price.current_price == 75.0
    assert "product:price:amount" in p._obs["detail"]


def test_visible_price_still_wins():
    html = (f'<html><head>{LD_GROUP}</head><body><main><h1>Canvas Cruiser</h1>'
            f'<div class="price"><span class="price-item price-item--regular">$70.00</span></div></main></body></html>')
    [p] = extract_products(BeautifulSoup(html, "html.parser"), URL, Platform.SHOPIFY, "product")
    assert p.price.current_price == 70.0


def test_no_price_anywhere_stays_none():
    assert _price("").price is None
