"""Batch 4: a site where no page returned 2xx is unknown (status=blocked), not False."""

import csv
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from tests.conftest import analyze_store
from modules.business_report import BusinessReportGenerator
from modules.models import Config
from modules.report_writer import ReportWriter
from modules.snapshot_store import SnapshotStore

UNKNOWN_FIELDS = ("platform", "currency", "price_min", "price_max", "price_median", "has_discounts",
                  "has_popup", "has_email_capture", "has_loyalty_program", "has_referral_program",
                  "review_platform", "total_reviews", "shipping_policy", "return_policy", "brand_positioning")
CSV_FIELDS = ("platform", "currency", "price_min", "price_max", "price_median", "has_discounts",
              "has_popup", "has_email_capture", "has_loyalty", "has_referral", "free_shipping_threshold",
              "return_days", "free_returns", "review_platform", "payment_methods", "pixels_detected",
              "brand_positioning")


@pytest.fixture(scope="module")
def blocked():
    return analyze_store("blocked")[0]


def test_blocked_site_is_unknown(blocked):
    assert blocked.status == "blocked"
    assert blocked.fetch_attempts == ["requests 403", "cloudscraper 403"]
    for name in UNKNOWN_FIELDS:
        assert getattr(blocked, name) is None, name
    assert blocked.payment_methods == [] and blocked.categories == []
    assert not [p for p in blocked.pixels if p.detected]


def test_blocked_with_render_js_lists_the_browser_branch():
    intel = analyze_store("blocked", render_js=True)[0]
    assert intel.status == "blocked"
    assert intel.fetch_attempts == ["browser 403", "cloudscraper 403"]


def test_ok_sites_have_status_ok(analyzed):
    assert {i.status for i in analyzed.values()} == {"ok"}


def _write(tmp_path, intel_list, lang="en"):
    md, csv_path = ReportWriter(str(tmp_path), language=lang).write_full_report(intel_list, {}, "report")
    biz = BusinessReportGenerator(str(tmp_path), language=lang).generate_report(intel_list, {}, {}, "business_report")
    rows = list(csv.DictReader(open(csv_path, encoding="utf-8-sig")))
    return Path(md).read_text(encoding="utf-8"), rows, Path(biz).read_text(encoding="utf-8")


def test_csv_has_status_column_and_empty_cells_for_blocked(tmp_path, analyzed, blocked):
    _, rows, _ = _write(tmp_path, [analyzed["shopify_basic"], blocked])
    assert [r["status"] for r in rows] == ["ok", "blocked"]
    assert rows[1]["fetch_attempts"] == "requests 403; cloudscraper 403"
    assert {f: rows[1][f] for f in CSV_FIELDS} == {f: "" for f in CSV_FIELDS}


def test_reports_say_blocked_and_leave_it_out_of_comparisons(tmp_path, analyzed, blocked):
    ok = [analyzed["shopify_basic"], analyzed["woocommerce_promo"]]
    md, _, biz = _write(tmp_path, ok + [blocked])

    assert "blocked automated access" in md and "requests (403) → cloudscraper (403)" in md
    table = md.split("Comparison Table", 1)[1]
    assert sum(1 for line in table.splitlines() if line.startswith("| 127.0.0.1")) == 2
    assert md.count("Competitive pressure score (rule-based)") == 2
    assert "custom or unidentified platform" not in md   # no rule-based insights for the blocked site

    assert "blocked automated access" in biz
    assert "**Competitors Analyzed:** 2" in biz
    assert " of 3 " not in biz and "(33%)" not in biz and "(66%)" not in biz


def test_only_blocked_sites(tmp_path, blocked):
    md, rows, biz = _write(tmp_path, [blocked])
    assert "blocked automated access" in md and "blocked automated access" in biz
    assert "**Competitors Analyzed:** 0" in biz
    assert "Pricing:" not in biz and "Free Shipping Gap" not in biz


def test_zh_report_says_blocked_in_chinese(tmp_path, blocked):
    md, _, biz = _write(tmp_path, [blocked], lang="zh")
    assert "阻止了自动访问" in md and "阻止了自动访问" in biz


def test_no_change_report_against_or_from_a_blocked_scan(tmp_path, analyzed, blocked):
    store = SnapshotStore(str(tmp_path / "intel.db"))
    ok = analyzed["shopify_basic"]
    assert store.compute_changes(blocked, ok.to_dict()) is None
    assert store.compute_changes(ok, blocked.to_dict()) is None


class PlaceholderClient:
    """HttpClient stand-in whose fetch fell through to the PROTECTED_SITES placeholder."""

    last_chain = [{"branch": "browser", "status": 403}, {"branch": "cloudscraper", "status": 403},
                  {"branch": "placeholder", "status": 200}]

    def fetch_and_parse(self, url, **kw):
        html = "<html><body><h1>Bot protection detected</h1><p>strong bot protection</p></body></html>"
        return BeautifulSoup(html, "html.parser"), 200, None

    def fetch(self, url, **kw):
        return None, 404, {}, "not used"


def test_protected_site_placeholder_is_reported_as_blocked():
    import main

    class AllowAll:
        def is_allowed(self, url):
            return True

        def get_sitemaps(self, url):
            return []

    intel = main.analyze_site("https://www.example-protected.test", PlaceholderClient(), AllowAll(),
                              Config(rate_limit_delay=0))
    assert intel.status == "blocked"
    assert intel.fetch_attempts == ["browser 403", "cloudscraper 403", "placeholder 200"]
    assert intel.platform is None and intel.has_popup is None
