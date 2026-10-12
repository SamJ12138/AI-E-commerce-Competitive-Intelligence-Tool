"""Collection cards that are themselves the product link (Phase 6; beardbrand, observations section 11).

beardbrand's collection pages draw each product as `<a class="product-item" href="/products/...">`
with `span.title` and `span.price` inside, in a `div[data-handle]` collection wrapper. The card
parser looked for the product link among the card's descendants only, so every card was dropped, and
the wrapper (matched by `[data-handle]`) became one product titled with the collection's heading and
the first card's link and price: 9 collection pages gave 9 products, one per page."""

from tests.page_server import analyze_pages, shopify_page

OILS = [("norse-winter-beard-oil", "Norse Winter Beard Oil", 32), ("bold-fortune-beard-oil", "Bold Fortune Beard Oil", 32),
        ("old-money-beard-oil", "Old Money Beard Oil", 29), ("tree-ranger-beard-oil", "Tree Ranger Beard Oil", 29),
        ("temple-smoke-beard-oil", "Temple Smoke Beard Oil", 29)]


def link_card(handle, title, price):
    """One card as beardbrand's theme draws it (trimmed): the whole card is the link."""
    return (f'<div class="site-box box--small box__collection"><div class="site-box-content product-holder">'
            f'<a aria-label="View product {title}" class="product-item style--one alt color--light" href="/products/{handle}">'
            f'<div aria-label="Product image of {title}" class="box--product-image primary" role="img">'
            f'<img alt="{title} - Featured Image" src="//cdn.example/{handle}.jpg?width=640"></div>'
            f'<div class="caption"><div><span class="title"><span class="underline-animation">{title}</span></span>'
            f'<span aria-label="Price: ${price}" class="price text-size--smaller"><span>From ${price}</span></span></div></div>'
            f'<span class="product-badge left rating"><span class="visually-hidden">Rating: 4.61 out of 5.0</span>'
            f'<span aria-hidden="true">4.6</span></span>'
            f'<span class="product-badge sold-out">Sold out</span></a></div></div>')


COLLECTION = shopify_page(
    '<div class="site-box-container container--fullscreen" data-handle="beard-oil">'
    '<div class="collection__holder"><h2 class="title">Beard Oil</h2><div class="product-grid-border-fix">'
    + "".join(link_card(*o) for o in OILS) + '</div></div></div>', "Beard Oil")
PAGES = {"/": shopify_page('<nav class="header__inline-menu"><ul><li><a href="/collections/beard-oil">Beard Oil</a>'
                           '</li></ul></nav><main><h1>Beardbrand-style store</h1></main>'),
         "/collections/beard-oil": COLLECTION}


def test_link_cards_are_products():
    intel, log = analyze_pages(PAGES)
    assert "/collections/beard-oil" in log
    got = [(p.url.rsplit("/", 1)[-1], p.title, p.price.current_price if p.price else None) for p in intel.all_products]
    assert got == [(h, t, float(pr)) for h, t, pr in OILS]


def test_the_collection_wrapper_is_not_a_product():
    intel, _ = analyze_pages(PAGES)
    assert "Beard Oil" not in [p.title for p in intel.all_products]
    assert (intel.price_min, intel.price_max) == (29.0, 32.0)


def test_card_with_an_inner_link_still_works():
    # the Dawn-style card (link inside the card), unchanged
    from tests.page_server import shopify_card
    pages = dict(PAGES)
    pages["/collections/beard-oil"] = shopify_page('<ul id="product-grid">' + shopify_card("trail-cap", "Trail Cap", 25.0)
                                                   + '</ul>')
    intel, _ = analyze_pages(pages)
    assert [(p.title, p.price.current_price) for p in intel.all_products] == [("Trail Cap", 25.0)]
