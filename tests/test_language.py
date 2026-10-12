"""Batch 3: --lang en writes no Chinese anywhere; --lang zh writes no English boilerplate.

Both stores are analysed once (conftest `analyzed`), a change report is produced the way
--monitor does, and all three reports are written in each language. Under zh, English is
allowed only where it is data from the site (quoted page text, names, URLs) or a product or
technical name in ALLOWED_NAMES.
"""

import copy
import re
from pathlib import Path

import pytest

from modules.business_report import BusinessReportGenerator
from modules.report_writer import ReportWriter
from modules.snapshot_store import SnapshotStore

CJK = re.compile(r"[　-〿㐀-鿿＀-￯]")
WORD = re.compile(r"[A-Za-z][A-Za-z'\-]+")
ALLOWED_NAMES = {"AI", "LLM", "Ollama", "USD", "Shopify", "WooCommerce", "BigCommerce", "Magento",
                 "Squarespace", "Wix", "PrestaShop", "WordPress", "Custom", "Unknown", "Google", "Analytics", "Meta",
                 "Pixel", "TikTok", "Pinterest", "Tag", "Snapchat", "PayPal", "Visa", "Mastercard",
                 "American", "Express", "Discover", "Klarna", "Afterpay", "Affirm", "Shop", "Pay",
                 "Apple", "Amazon", "Venmo", "Sezzle", "Yotpo", "Judge", "me", "robots", "txt", "FAQ",
                 "CSV", "JSON", "HTML", "URL", "SWOT"}


def _write_all(intel_list, changes, lang, out):
    md, csv_path = ReportWriter(str(out), language=lang).write_full_report(intel_list, changes, "report")
    biz = BusinessReportGenerator(str(out), language=lang).generate_report(intel_list, changes, {}, "business_report")
    return {name: Path(p).read_text(encoding="utf-8-sig") for name, p in
            (("report.md", md), ("report.csv", csv_path), ("business_report.md", biz))}


@pytest.fixture(scope="module")
def scans(analyzed, tmp_path_factory):
    """Both stores plus a change report against a doctored previous scan of each."""
    store = SnapshotStore(str(tmp_path_factory.mktemp("db") / "intel.db"))
    intel_list = [analyzed["shopify_basic"], analyzed["woocommerce_promo"]]
    previous = {}
    for intel in intel_list:
        old = copy.deepcopy(intel.to_dict())
        old["price_max"] = (intel.price_max or 0) + 10
        old["categories"] = old["categories"] + ["Old Category"]
        old["scan_timestamp"] = "2026-01-01T00:00:00"
        previous[intel.domain] = old
    return intel_list, store, previous


def _changes(scans, lang):
    intel_list, store, previous = scans
    return {i.domain: store.compute_changes(i, previous[i.domain], language=lang) for i in intel_list}


def _site_tokens(intel_list):
    """Words that come from the sites themselves."""
    tokens = set()
    for intel in intel_list:
        values = [intel.domain, intel.url, intel.brand_name, intel.brand_positioning or "",
                  intel.announcement_bar_text, intel.review_platform, " ".join(intel.categories),
                  " ".join(intel.payment_methods), " ".join(p.title for p in intel.all_products),
                  " ".join(p.name for p in intel.pixels), "Old Category"]
        for v in values:
            tokens |= set(WORD.findall(v or ""))
    return tokens


def test_en_reports_contain_no_chinese(scans, tmp_path):
    files = _write_all(scans[0], _changes(scans, "en"), "en", tmp_path)
    for name, text in files.items():
        hits = sorted({m.group(0) for m in CJK.finditer(text)})
        assert not hits, f"{name} (--lang en) contains Chinese: {''.join(hits)[:60]}"


def test_zh_reports_contain_no_english_boilerplate(scans, tmp_path):
    files = _write_all(scans[0], _changes(scans, "zh"), "zh", tmp_path)
    allowed = ALLOWED_NAMES | _site_tokens(scans[0])
    for name in ("report.md", "business_report.md"):
        text = files[name]
        text = re.sub(r"https?://\S+", " ", text)          # URLs
        text = re.sub(r"“[^”]*”|`[^`]*`", " ", text)        # quoted page text, code
        words = sorted({w for w in WORD.findall(text) if w not in allowed})
        assert not words, f"{name} (--lang zh) contains English: {words[:30]}"


def test_change_lines_follow_the_language(scans):
    en = _changes(scans, "en")
    zh = _changes(scans, "zh")
    for domain, report in en.items():
        lines = report.price_changes + report.category_changes
        assert lines and not any(CJK.search(line) for line in lines), lines
        assert any(CJK.search(line) for line in zh[domain].price_changes)
