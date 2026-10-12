"""Stratified product sampling: at most max_products_per_collection products from each collection,
total cap unchanged (Phase 5 Batch 1; allbirds' first collection gave 194 products and every other
collection and product page was skipped, so the price range was that one collection's)."""

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
    intel, _ = analyze_pages(THREE)
    assert _bands(intel) == {"budget": 10, "core": 10, "premium": 10}
    assert len(intel.all_products) == 30


def test_total_cap_unchanged():
    intel, log = analyze_pages(THREE, max_products=25)
    assert len(intel.all_products) == 25
    assert _bands(intel) == {"budget": 10, "core": 10, "premium": 5}


def test_per_collection_setting():
    intel, _ = analyze_pages(THREE, max_products_per_collection=3)
    assert _bands(intel) == {"budget": 3, "core": 3, "premium": 3}


def test_price_stats_are_over_the_sample():
    intel, _ = analyze_pages(THREE, max_products_per_collection=2)
    prices = sorted(p.price.current_price for p in intel.all_products)
    assert prices == [5.0, 5.25, 40.0, 40.25, 200.0, 200.25]
    assert (intel.price_min, intel.price_max) == (5.0, 200.25)
    assert intel.price_median == (40.0 + 40.25) / 2


def test_sample_is_recorded():
    intel, _ = analyze_pages(THREE)
    assert intel.product_sample == {"products": 30, "collections": 3, "per_collection": 10,
                                    "homepage": 0, "product_pages": 0, "feed": 0}


def test_reports_state_the_sample(tmp_path):
    from modules.business_report import BusinessReportGenerator
    from modules.report_writer import ReportWriter
    intel, _ = analyze_pages(THREE)
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
    intel, _ = analyze_pages(pages)
    urls = {p.url.rsplit("/", 1)[-1]: p.price.current_price for p in intel.all_products}
    assert urls.get("field-mug") == 38.0 and urls.get("trail-cap") == 25.0
    assert intel.product_sample["homepage"] == 2
    assert intel.product_sample["products"] == 32


def test_config_key_and_cli_option():
    assert main.CONFIG_KEYS["max_products_per_collection"] == 10
    from click.testing import CliRunner
    out = CliRunner().invoke(main.main, ["--help"]).output
    assert "--max-per-collection" in out
