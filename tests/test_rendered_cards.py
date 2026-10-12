"""Product cards as a browser renders them (Phase 5 Batch 2, the first real --render-js run:
brooklinen). The image link carries a text badge ("Best Seller", "Cooling") and comes before the
title link; the struck-through price is a span with a "--slashout" class, not <s> or <del>."""

from bs4 import BeautifulSoup

from modules.models import Platform
from modules.product_extractor import extract_products

CARD = """<article class="js-product-card ProductCard" itemscope itemtype="https://schema.org/Product">
 <div class="ProductCard-ImageWrapper">
  <a aria-hidden="true" tabindex="-1" href="/products/{handle}?variant=1">
   <div class="ProductCard__Badges"><div class="ProductCard__TextBadgeWrapper">
    <span class="ProductCard__TextBadge t5">{badge}</span></div></div>
   <img src="/cdn/{handle}.jpg" alt="">
  </a>
 </div>
 <div class="ProductCard__Title-Container">
  <a href="/products/{handle}?variant=1"><div class="Eyebrow__Container"></div><p class="t2">{title}</p></a>
  <wishlist-btn class="Wishlist" role="button"></wishlist-btn>
 </div>
 <a href="/products/{handle}?variant=1"><div class="PricePill__Container"><p class="Price p4 --product-card">
  <span><span class="Price__From from --show">From:</span>
  <span class="Price__Default t4 --slashout">${was}</span>
  <span class="Price__Discounted t4 js-price-variant">${now}</span></span></p>
  <span class="PricePill__Discount">15% off</span></div></a>
</article>"""


def _cards(*cards):
    html = '<html><body><main><div class="ProductGrid">' + "".join(cards) + "</div></main></body></html>"
    return extract_products(BeautifulSoup(html, "html.parser"), "https://shop.example/collections/best-sellers",
                            Platform.SHOPIFY, "collection")


def test_title_is_not_the_badge():
    [p] = _cards(CARD.format(handle="down-comforter", badge="Best Seller", title="Down Comforter", was=199, now=169))
    assert p.title == "Down Comforter"
    assert p.url == "https://shop.example/products/down-comforter?variant=1"


def test_slashout_price_is_the_compare_at_price():
    [p] = _cards(CARD.format(handle="waffle-robe", badge="Cooling", title="Dreamweave Waffle Robe", was=139, now=118))
    assert p.title == "Dreamweave Waffle Robe"
    assert p.price.current_price == 118.0
    assert p.price.compare_at_price == 139.0
    assert p.price.is_on_sale is True and p.price.discount_percent == 15


def test_card_without_a_badge_or_discount():
    card = (CARD.format(handle="down-pillow", badge="", title="Down Pillow", was=0, now=139)
            .replace('<span class="Price__Default t4 --slashout">$0</span>', ""))
    [p] = _cards(card)
    assert p.title == "Down Pillow"
    assert p.price.current_price == 139.0 and p.price.compare_at_price is None
