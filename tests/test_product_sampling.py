"""Stratified product sampling: at most max_products_per_collection products from each collection,
total cap unchanged (Phase 5 Batch 1; allbirds' first collection gave 194 products and every other
collection and product page was skipped, so the price range was that one collection's). When the
quota leaves the sample under the cap, it is topped up from the collection pages already fetched, in
crawl order, with no further request (Phase 6; barefootbuttons has one collection)."""

from pathlib import Path

import main
from modules.models import Config
from tests.page_server import analyze_pages, shopify_card, shopify_page

BANDS = {"budget": 5.0, "core": 40.0, "premium": 200.0}  # first price of each collection
PER_PAGE = 60  # more than the total cap, so the first collection alone used to fill it


def _collection(name, start):
    cards = "".join(shopify_card(f"{name}-{i}", f"{name.title()} item {i}", start + i * 0.25)
                    for i in range(PER_PAGE))
    return shopify_page(f'<h1>{name.title()}</h1><ul id="product-grid">{cards}</ul>', name.title())


NAV = ('<nav class="header__inline-menu"><ul>'
       + "".join(f'<li><a href="/collections/{n}">{n.title()}</a></li>' for n in BANDS)
       + '</ul></nav>')
THREE = {"/": shopify_page(NAV + "<main><h2>Welcome</h2></main>"),
         **{f"/collections/{n}": _collection(n, s) for n, s in BANDS.items()}}


def _bands(intel):
    out = {}
    for p in intel.all_products:
        name = p.url.rsplit("/", 1)[-1].rsplit("-", 1)[0]
        out[name] = out.get(name, 0) + 1
    return out


def test_price_range_spans_all_three_collections():
    intel, log = analyze_pages(THREE)
    assert [p for p in log if p.startswith("/collections/")] == [f"/collections/{n}" for n in BANDS]
    assert BANDS["budget"] <= intel.price_min < BANDS["core"]
    assert intel.price_max >= BANDS["premium"]


def test_at_most_n_per_collection_by_default():
    assert Config.max_products_per_collection == 10
    intel, _ = analyze_pages(THREE, max_products=30)
    assert _bands(intel) == {"budget": 10, "core": 10, "premium": 10}
    assert len(intel.all_products) == 30


def test_top_up_follows_crawl_order():
    # 3 x 10 by quota, then the 20 left to the cap of 50 from the first collection read
    intel, log = analyze_pages(THREE)
    assert _bands(intel) == {"budget": 30, "core": 10, "premium": 10}
    assert [p.url.rsplit("/", 1)[-1] for p in intel.all_products[:10]] == [f"budget-{i}" for i in range(10)]
    assert sorted(p for p in log if p.startswith("/collections/")) == sorted(f"/collections/{n}" for n in BANDS)


def test_total_cap_unchanged():
    intel, log = analyze_pages(THREE, max_products=25)
    assert len(intel.all_products) == 25
    assert _bands(intel) == {"budget": 10, "core": 10, "premium": 5}


def test_per_collection_setting():
    intel, _ = analyze_pages(THREE, max_products=9, max_products_per_collection=3)
    assert _bands(intel) == {"budget": 3, "core": 3, "premium": 3}


def test_price_stats_are_over_the_sample():
    intel, _ = analyze_pages(THREE, max_products=6, max_products_per_collection=2)
    prices = sorted(p.price.current_price for p in intel.all_products)
    assert prices == [5.0, 5.25, 40.0, 40.25, 200.0, 200.25]
    assert (intel.price_min, intel.price_max) == (5.0, 200.25)
    assert intel.price_median == (40.0 + 40.25) / 2


def test_sample_is_recorded():
    intel, _ = analyze_pages(THREE)
    assert intel.product_sample == {"products": 50, "collections": 3, "per_collection": 10,
                                    "homepage": 0, "product_pages": 0, "feed": 0, "topped_up": 20}


# One collection (barefootbuttons: its only product source is /shop): the quota alone gave 10.
ONE = {"/": shopify_page('<nav class="header__inline-menu"><ul><li><a href="/collections/all">Shop</a></li>'
                         '</ul></nav><main><h2>Welcome</h2></main>'),
       "/collections/all": shopify_page('<ul id="product-grid">' + "".join(
           shopify_card(f"item-{i}", f"Item {i}", 9.95 + i) for i in range(30)) + '</ul>', "Shop")}


def test_one_collection_of_30_gives_30():
    intel, log = analyze_pages(ONE)
    assert len(intel.all_products) == 30
    assert [p.url.rsplit("/", 1)[-1] for p in intel.all_products] == [f"item-{i}" for i in range(30)]
    assert (intel.price_min, intel.price_max) == (9.95, 38.95)
    assert intel.product_sample["topped_up"] == 20
    assert log.count("/collections/all") == 1  # no extra request: the page already read


def test_top_up_never_passes_the_cap():
    intel, _ = analyze_pages(ONE, max_products=25)
    assert len(intel.all_products) == 25
    assert intel.product_sample["topped_up"] == 15


def test_reports_state_the_top_up(tmp_path):
    from modules.report_writer import ReportWriter
    intel, _ = analyze_pages(ONE)
    md, _csv = ReportWriter(str(tmp_path), language="en").write_full_report([intel], {intel.domain: None})
    text = Path(md).read_text(encoding="utf-8")
    assert "30 products from 1 collection (10 per collection, then 20 more from the collections read)" in text
    md_zh, _ = ReportWriter(str(tmp_path / "zh"), language="zh").write_full_report([intel], {intel.domain: None})
    assert "30个产品，来自1个产品集合（每个10个，另从已读集合补充20个）" in Path(md_zh).read_text(encoding="utf-8")


def test_reports_state_the_sample(tmp_path):
    from modules.business_report import BusinessReportGenerator
    from modules.report_writer import ReportWriter
    intel, _ = analyze_pages(THREE, max_products=30)
    md, _csv = ReportWriter(str(tmp_path), language="en").write_full_report([intel], {intel.domain: None})
    expected = "30 products from 3 collections (at most 10 per collection)"
    assert expected in Path(md).read_text(encoding="utf-8")
    biz = BusinessReportGenerator(str(tmp_path), language="en").generate_report(
        [intel], {}, {}, "business_report", run_info={"ignore_robots": False, "render_js": False})
    assert expected in Path(biz).read_text(encoding="utf-8")
    md_zh, _ = ReportWriter(str(tmp_path / "zh"), language="zh").write_full_report([intel], {intel.domain: None})
    assert "30个产品，来自3个产品集合" in Path(md_zh).read_text(encoding="utf-8")


# The homepage's own product cards are a source too (deathwishcoffee: the mug in the ground truth
# was a homepage card; its product page and its collection were beyond max_pages).
FEATURED = "".join(shopify_card(h, t, p) for h, t, p in
                   [("field-mug", "Field Mug", 38.0), ("trail-cap", "Trail Cap", 25.0)])


def test_homepage_product_cards_are_sampled():
    pages = dict(THREE)
    pages["/"] = shopify_page(NAV + f'<main><h2>Featured</h2><ul class="grid">{FEATURED}</ul></main>')
    intel, _ = analyze_pages(pages, max_products=32)
    urls = {p.url.rsplit("/", 1)[-1]: p.price.current_price for p in intel.all_products}
    assert urls.get("field-mug") == 38.0 and urls.get("trail-cap") == 25.0
    assert intel.product_sample["homepage"] == 2
    assert intel.product_sample["products"] == 32


def test_config_key_and_cli_option():
    assert main.CONFIG_KEYS["max_products_per_collection"] == 10
    from click.testing import CliRunner
    out = CliRunner().invoke(main.main, ["--help"]).output
    assert "--max-per-collection" in out
