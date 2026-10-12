"""Batch 5: the business report says only what the data supports.

One store, two stores, and two stores plus the blocked one. Comparative sentences depend on
the number of analysed (non-blocked) sites; the methodology states what actually ran.
"""

import re
from pathlib import Path

import pytest

from modules.business_report import BusinessReportGenerator
from tests.conftest import analyze_store

RUN = {"ignore_robots": False, "render_js": False, "ai_requested": False, "ai_available": False,
       "ai_model": "qwen2.5:7b"}


@pytest.fixture(scope="module")
def blocked():
    return analyze_store("blocked")[0]


def _biz(tmp_path, intel_list, lang="en", **run):
    path = BusinessReportGenerator(str(tmp_path), language=lang).generate_report(
        intel_list, {}, {}, "business_report", run_info=dict(RUN, **run))
    return Path(path).read_text(encoding="utf-8")


def test_one_site_makes_no_market_or_competitor_claims(tmp_path, analyzed):
    text = _biz(tmp_path, [analyzed["shopify_basic"]])
    for banned in (r"competitor", r"multiple players", r"\baverage\b", r"market spans", r"\bmarket\b",
                   r"\(\d+%\)", r"\d+ of 1\b", r"Shopify ecosystem", r"similar price ranges"):
        assert not re.search(banned, text, re.I), banned
    assert "**Sites Analyzed:** 1" in text
    assert "$24-$39" in text and "$50" in text and "30-day" in text


def test_two_sites_compare_with_counts(tmp_path, analyzed):
    text = _biz(tmp_path, [analyzed["shopify_basic"], analyzed["woocommerce_promo"]])
    assert "**Sites Analyzed:** 2" in text
    assert "2 of 2" in text                      # both offer free shipping over a threshold
    assert re.search(r"price ranges overlap", text, re.I)
    assert "Shopify ecosystem" not in text       # one Shopify, one WooCommerce
    assert not re.search(r"multiple players", text, re.I)


def test_two_sites_plus_blocked_counts_two(tmp_path, analyzed, blocked):
    text = _biz(tmp_path, [analyzed["shopify_basic"], analyzed["woocommerce_promo"], blocked])
    assert "**Sites Analyzed:** 2" in text
    assert "blocked automated access" in text.lower()
    assert " of 3" not in text and "(33%)" not in text


def test_methodology_states_what_ran(tmp_path, analyzed):
    shop = analyzed["shopify_basic"]
    text = _biz(tmp_path, [shop])
    method = text.split("### Methodology", 1)[1]
    assert f"{len(shop.pages_crawled)} pages" in method
    assert "requests" in method                  # the fetch branch that served the pages
    assert "robots.txt was respected" in method
    assert "LLM step was not run" in method
    assert "Qwen" not in text and "AI-powered" not in text


def test_methodology_ignore_robots_and_ai_unavailable(tmp_path, analyzed):
    text = _biz(tmp_path, [analyzed["shopify_basic"]], ignore_robots=True, ai_requested=True)
    method = text.split("### Methodology", 1)[1]
    assert "robots.txt was ignored" in method and "respecting robots.txt" not in text
    assert "requested" in method and "not available" in method and "qwen2.5:7b" in method


def test_methodology_names_the_model_when_the_llm_ran(tmp_path, analyzed):
    import copy
    shop = copy.deepcopy(analyzed["shopify_basic"])
    shop.ai_model, shop.ai_insights = "qwen2.5:7b", {"key_insights": ["x"], "raw_response": "x"}
    text = _biz(tmp_path, [shop], ai_requested=True, ai_available=True)
    method = text.split("### Methodology", 1)[1]
    assert "qwen2.5:7b" in method and "1 of 1" not in method


def test_ai_prompt_uses_only_fields_the_pipeline_produces(analyzed):
    from modules.ai_analyzer import ChineseInsightGenerator
    prompt = ChineseInsightGenerator(None)._build_prompt(analyzed["shopify_basic"].to_dict())
    assert "N/A" not in prompt
    assert "$50" in prompt and "30天" in prompt          # nested shipping/return policy values
    assert "威胁" not in prompt and "定价策略" not in prompt  # sections nothing prints
    blocked_prompt = ChineseInsightGenerator(None)._build_prompt(
        {"domain": "x", "platform": None, "categories": [], "payment_methods": []})
    assert "N/A" not in blocked_prompt and "None" not in blocked_prompt
