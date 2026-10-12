"""No price range from the homepage text (Phase 6).

Until Phase 6, a run in which no product had a price took the range from every dollar amount
written in the homepage HTML, so free-shipping thresholds and gift-card values became prices
(brooklinen's default run: $25-$500). Now a store with no priced product reports the price fields
as null, with a note in the reports saying why."""

import importlib
import json
from pathlib import Path

from tests.page_server import analyze_pages, shopify_page

# Product pages with no price (none visible, none in structured data); the homepage text has a
# threshold, gift-card amounts and two prices written in a paragraph, not on product cards.
PAGES = {
    "/": shopify_page('<div class="announcement-bar">Free shipping on orders over $75</div>'
                      '<main><h1>Field Supply</h1><p>Canvas Tote - $28.00</p><p>Linen Shirt - $48.00</p>'
                      '<p>Gift cards from $25 to $500</p>'
                      '<a href="/products/canvas-tote">Canvas Tote</a>'
                      '<a href="/products/linen-shirt">Linen Shirt</a></main>'),
    "/products/canvas-tote": shopify_page("<main><h1>Canvas Tote</h1><p>Sturdy cotton canvas.</p></main>"),
    "/products/linen-shirt": shopify_page("<main><h1>Linen Shirt</h1><p>Washed linen.</p></main>"),
}


def test_no_priced_product_gives_null_price_fields():
    intel, log = analyze_pages(PAGES)
    assert "/products/canvas-tote" in log and "/products/linen-shirt" in log
    assert all(p.price is None or p.price.current_price is None for p in intel.all_products)
    assert (intel.price_min, intel.price_max, intel.price_median, intel.currency) == (None, None, None, None)
    assert intel.price_note == "no_priced_product"
    assert intel.to_dict()["price_note"] == "no_priced_product"


def test_homepage_fallback_is_gone():
    pe = importlib.import_module("modules.product_extractor")
    for name in ("homepage_price_fallback", "HOMEPAGE_AMOUNT_PATTERNS", "PAGE_CURRENCY_PATTERNS"):
        assert not hasattr(pe, name)


def test_reports_say_why_the_price_is_missing(tmp_path):
    from modules.business_report import BusinessReportGenerator
    from modules.report_writer import ReportWriter
    intel, _ = analyze_pages(PAGES)
    md, csv_path = ReportWriter(str(tmp_path), language="en").write_full_report([intel], {intel.domain: None})
    text = Path(md).read_text(encoding="utf-8")
    note = "not reported (no product read had a price"
    assert "Price range: " + note in text
    for amount in ("$25", "$500", "$75 -", "$28.00 - $48.00"):
        assert f"Price range: {amount}" not in text
    biz = BusinessReportGenerator(str(tmp_path), language="en").generate_report(
        [intel], {}, {}, "business_report", run_info={"ignore_robots": False, "render_js": False})
    assert note in Path(biz).read_text(encoding="utf-8")
    import csv
    row = next(csv.DictReader(open(csv_path, encoding="utf-8-sig")))
    assert (row["price_min"], row["price_max"], row["price_median"]) == ("", "", "")
    md_zh, _ = ReportWriter(str(tmp_path / "zh"), language="zh").write_full_report([intel], {intel.domain: None})
    assert "价格区间: 未报告（所读产品均无价格" in Path(md_zh).read_text(encoding="utf-8")


def test_priced_store_has_no_note():
    from tests.page_server import shopify_card
    pages = dict(PAGES)
    pages["/"] = shopify_page('<ul class="grid">' + shopify_card("canvas-tote", "Canvas Tote", 28.0) + "</ul>")
    intel, _ = analyze_pages(pages)
    assert (intel.price_min, intel.price_max) == (28.0, 28.0)
    assert intel.price_note is None
