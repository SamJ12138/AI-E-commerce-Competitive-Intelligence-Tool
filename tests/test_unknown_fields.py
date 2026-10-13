"""A field the scan could not determine (None) never turns into a negative claim.

Three-way wording wherever a report sentence is chosen on a field that can be unknown:
True states it, False states the negative, None omits the sentence or says "not determined".
Both report writers (business_report.md and report.md with its rule-based insights) are checked,
and a stored snapshot can be loaded back so a report can be rebuilt without a new scan.
"""

import re
import sys
from datetime import datetime
from pathlib import Path

import pytest

from modules.business_report import BusinessReportGenerator
from modules.insight_generator import InsightGenerator
from modules.models import (AnalyticsPixel, PriceInfo, Product, Promotion, ReturnPolicy, ShippingPolicy,
                            SiteIntelligence, TrustSignal)
from modules.report_writer import ReportWriter
from modules.snapshot_store import SnapshotStore

REPO = Path(__file__).resolve().parent.parent
RUN = {"ignore_robots": False, "render_js": False, "ai_requested": False, "ai_available": False,
       "ai_model": "qwen2.5:7b"}
SCANNED = datetime(2026, 10, 12, 20, 37, 45)

# Negative wording in either language. "No recommendation: ..." is about the data, not a field.
NEGATIVE = {"en": re.compile(r"without|\bno\b|does not|doesn't|\bnone\b|\b0 of\b|not free|❌|paid shipping", re.I),
            "zh": re.compile(r"不使用|未发现|不提供|没有|都不|❌|有运费")}
NO_REC = {"en": "No recommendation", "zh": "无建议"}


def unknown_site_dict(domain="unknown.example"):
    """An analysed site whose every optional field is None (platform kept: it is what made it a store)."""
    d = SiteIntelligence(domain=domain, url=f"https://{domain}", scan_timestamp=SCANNED,
                         platform=None).to_dict()
    for name in SiteIntelligence.UNKNOWN_WHEN_BLOCKED:
        d[name] = None
    d.update(platform="Shopify", platform_confidence=0.9, status="ok", pages_crawled=[f"https://{domain}/"])
    return d


def _biz(tmp_path, sites, lang="en"):
    path = BusinessReportGenerator(str(tmp_path), language=lang).generate_report(
        sites, {}, {}, "business_report", run_info=RUN)
    return Path(path).read_text(encoding="utf-8")


def _claims(text, lang):
    """Report lines before the appendix (the appendix describes the run, not the site)."""
    body = text.split("## Appendix" if lang == "en" else "## 附录")[0]
    return [line for line in body.splitlines() if line.strip() and NO_REC[lang] not in line]


# ------------------------------------------------------------------ snapshots

def _full_intel():
    return SiteIntelligence(
        domain="shop.example", url="https://shop.example", scan_timestamp=SCANNED,
        fetch_branches={"requests": 12}, platform_signals=["cdn.shopify.com"], categories=["Shoes"],
        all_products=[Product("Runner", "https://shop.example/p/1",
                              price=PriceInfo(current_price=98.0, compare_at_price=120.0, is_on_sale=True,
                                              discount_percent=18.3), review_count=4)],
        product_sample={"products": 1, "homepage": 1}, price_min=98.0, price_max=98.0, price_median=98.0,
        promotions=[Promotion("announcement_bar", "Free shipping over $75", "$75")],
        announcement_bar_text="Free shipping over $75", has_popup=None, has_email_capture=True,
        pixels=[AnalyticsPixel("Meta Pixel", True, "123")], trust_signals=[TrustSignal("badge", "SSL")],
        review_platform="Yotpo", total_reviews=40, payment_methods=["Visa"],
        shipping_policy=ShippingPolicy(free_shipping_threshold=75.0, evidence_source="faq", evidence_level=2),
        return_policy=ReturnPolicy(return_days=30, free_returns=None, evidence_source="policy_page"),
        pages_crawled=["https://shop.example/"], errors=["robots.txt disallows /policies/shipping-policy"])


def test_snapshot_dict_loads_back_to_the_same_site():
    d = _full_intel().to_dict()
    back = SiteIntelligence.from_dict(d)
    assert back.to_dict() == d
    assert back.scan_timestamp == SCANNED and back.has_popup is None
    assert back.all_products[0].price.current_price == 98.0
    assert back.shipping_policy.evidence_level == 2 and back.return_policy.free_returns is None


def test_snapshot_dict_from_the_ad_hoc_shipping_policy_loads():
    """main.py can store a shipping policy dict without the evidence keys."""
    d = _full_intel().to_dict()
    d["shipping_policy"] = {"free_shipping_threshold": 50.0, "regions": ["United States"],
                            "estimated_days_min": None, "estimated_days_max": None,
                            "has_international": False, "raw_text": ""}
    assert SiteIntelligence.from_dict(d).shipping_policy.free_shipping_threshold == 50.0


# ------------------------------------------------------------------ business_report.md

@pytest.mark.parametrize("lang", ["en", "zh"])
@pytest.mark.parametrize("n", [1, 2])
def test_unknown_fields_make_no_negative_claim_in_the_business_report(tmp_path, lang, n):
    sites = [SiteIntelligence.from_dict(unknown_site_dict(f"s{i}.example")) for i in range(n)]
    text = _biz(tmp_path, sites, lang)
    bad = [line for line in _claims(text, lang) if NEGATIVE[lang].search(line)]
    assert not bad, bad


def _one(**kw):
    d = unknown_site_dict()
    d.update(kw)
    return SiteIntelligence.from_dict(d)


@pytest.mark.parametrize("popup, expected", [
    (True, "this site collects emails with a popup."),
    (False, "this site collects emails without a popup."),
    (None, "this site collects emails."),
])
def test_email_capture_recommendation_is_three_way(tmp_path, popup, expected):
    text = _biz(tmp_path, [_one(has_email_capture=True, has_popup=popup)])
    assert f"**Email capture:** {expected}" in text


@pytest.mark.parametrize("popup, expected", [(True, "该站点通过弹窗收集邮件。"), (False, "该站点不使用弹窗收集邮件。"),
                                             (None, "该站点收集邮件。")])
def test_email_capture_recommendation_is_three_way_zh(tmp_path, popup, expected):
    assert expected in _biz(tmp_path, [_one(has_email_capture=True, has_popup=popup)], "zh")


@pytest.mark.parametrize("loyalty, expected", [(True, "**Loyalty:** runs a loyalty program."),
                                               (False, "**Loyalty:** no loyalty program found."),
                                               (None, "**Loyalty:** not determined.")])
def test_loyalty_finding_is_three_way(tmp_path, loyalty, expected):
    assert expected in _biz(tmp_path, [_one(has_loyalty_program=loyalty)])


def test_counts_leave_unknown_sites_out(tmp_path):
    sites = [_one(has_loyalty_program=True, has_subscriptions=True),
             _one(has_loyalty_program=False, has_subscriptions=False),
             _one(has_loyalty_program=None, has_subscriptions=None)]
    for i, s in enumerate(sites):
        s.domain, s.url = f"s{i}.example", f"https://s{i}.example"
    text = _biz(tmp_path, sites)
    assert "**Loyalty:** 1 of 2 sites run a loyalty program (not determined for 1)." in text
    assert "1 of 2 sites sell subscriptions (not determined for 1)." in text
    rows = {line.split(" | ")[0][2:]: line for line in text.splitlines() if line.startswith("| s")}
    assert rows["s0.example"].endswith("| ✅ | ✅ |")
    assert rows["s1.example"].endswith("| ❌ | ❌ |")
    assert rows["s2.example"].endswith("| N/A | N/A |")


def test_returns_and_shipping_not_read_are_not_determined(tmp_path):
    text = _biz(tmp_path, [_one()])
    assert "**Shipping:** not determined." in text and "**Returns:** not determined." in text
    read = _biz(tmp_path, [_one(shipping_policy={"free_shipping_threshold": None},
                                return_policy={"return_days": None})])
    assert "**Shipping:** no free-shipping offer found." in read
    assert "**Returns:** no return window found." in read


def test_report_date_can_be_the_scan_date(tmp_path):
    path = BusinessReportGenerator(str(tmp_path), language="en").generate_report(
        [_one()], {}, {}, "business_report", run_info=RUN, report_date=SCANNED)
    assert "**Report Date:** October 12, 2026" in Path(path).read_text(encoding="utf-8")


# ------------------------------------------------------------------ report.md

@pytest.mark.parametrize("lang", ["en", "zh"])
def test_unknown_fields_make_no_negative_claim_in_the_comparison_row(tmp_path, lang):
    row = ReportWriter(str(tmp_path), language=lang)._generate_table_row(_one())
    promotions, shipping, trust, key_point = row[5], row[6], row[8], row[9]
    for cell in (promotions, shipping, trust, key_point):
        assert not NEGATIVE[lang].search(cell), (row, cell)


def test_comparison_row_states_known_negatives(tmp_path):
    known = _one(has_popup=False, has_email_capture=False, has_loyalty_program=False, announcement_bar_text="",
                 review_platform="", has_subscriptions=False, has_bundles=False,
                 shipping_policy={"free_shipping_threshold": None})
    row = ReportWriter(str(tmp_path), language="en")._generate_table_row(known)
    assert row[5] == "None" and row[8] == "None" and row[9] == "None"
    assert row[6] == "No free-shipping offer found"


@pytest.mark.parametrize("lang", ["en", "zh"])
def test_rule_based_recommendations_do_not_guess(lang):
    recs = InsightGenerator(lang).generate_insights(_one(has_email_capture=True))["recommendations"]
    text = " ".join(recs)
    assert not re.search(r"without a popup|No review system|不使用弹窗|评论系统不明显", text), recs


def test_rule_based_recommendations_keep_known_negatives():
    recs = InsightGenerator("en").generate_insights(
        _one(has_email_capture=True, has_popup=False, review_platform=""))["recommendations"]
    assert any("without a popup" in r for r in recs) and any("No review system" in r for r in recs)


# ------------------------------------------------------------------ demo rebuild

def test_demo_report_is_rebuilt_from_the_stored_snapshot(tmp_path):
    sys.path.insert(0, str(REPO / "scripts"))
    import make_demo_video as mdv

    run_dir = tmp_path / "run"
    (run_dir / "data").mkdir(parents=True)
    SnapshotStore(str(run_dir / "data" / "intel_cache.db")).save_snapshot(_full_intel())
    out = mdv.rebuild_report(run_dir, tmp_path / "rebuilt")
    text = out.read_text(encoding="utf-8")
    assert out.name == "business_report.md"
    assert "**Report Date:** October 12, 2026" in text and "**Sites Analyzed:** 1" in text
    assert "**Email capture:** this site collects emails." in text
    assert not (run_dir / "output").exists()
