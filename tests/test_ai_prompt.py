"""The AI prompt and its parser (Phase 8 Batch 2). One call per store asks for a positioning summary,
three risks and three opportunities, each citing a field the prompt listed as [field: value]. A
response that does not have that shape is a parse failure, and the reports then say "AI analysis
unavailable" instead of printing the text."""

import json
from datetime import datetime
from pathlib import Path

import pytest

from modules import ai_analyzer, obs
from modules.models import Platform, ReturnPolicy, ShippingPolicy, SiteIntelligence

DATA = {
    "domain": "example.com", "url": "https://example.com", "platform": "Shopify", "status": "ok",
    "brand_name": "Example", "brand_positioning": "Comfortable shoes made from wool.",
    "categories": ["Shoes", "Socks"], "price_min": 14.0, "price_max": 145.0, "price_median": 105.0,
    "currency": "USD", "has_discounts": True, "announcement_bar_text": "", "has_popup": None,
    "has_email_capture": True, "has_loyalty_program": False, "has_referral_program": None,
    "review_platform": "Yotpo", "total_reviews": None, "payment_methods": ["Visa", "PayPal", "Shop Pay"],
    "product_sample": {"products": 50, "collections": 5},
    "shipping_policy": {"free_shipping_threshold": 100.0}, "return_policy": {"return_days": 30, "free_returns": False},
}

CLEAN = """## Positioning
A premium natural-materials shoe brand [brand_positioning: Comfortable shoes made from wool.] priced mostly near the top of its range [price_median: $105].

## Risks
1. Free shipping starts at $100, so most single pairs ship free [free_shipping_threshold: $100].
2. They take ten payment options including PayPal [payment_methods: Visa, PayPal, Shop Pay].
3. Yotpo reviews build trust [review_platform: Yotpo].

## Opportunities
1. Returns are not free, so free returns would stand out [free_returns: no].
2. No loyalty program was found [has_loyalty: no].
3. Entry products start at $14 [price_min: $14].
"""

EXTRA_PROSE = """Sure! Here is my analysis of the store, based only on the data you gave me.

**Positioning**
A premium natural-materials shoe brand [brand_positioning: Comfortable shoes made from wool.].

**Risks**
- Free shipping over $100 [free_shipping_threshold: $100]
- Many payment options [payment_methods: Visa, PayPal, Shop Pay]
- Reviews through Yotpo [review_platform: Yotpo]

**Opportunities**
- Paid returns [free_returns: no]
- No loyalty program [has_loyalty: no]
- Low entry price [price_min: $14]

I hope this helps. Let me know if you would like a deeper look at pricing.
"""

TRUNCATED = """## Positioning
A premium natural-materials shoe brand [brand_positioning: Comfortable shoes made from wool.].

## Risks
1. Free shipping over $100 [free_shipping_threshold: $100].
2. Many payment options [payment_methods: Visa, PayPal, Shop Pay].
3. Reviews through Yotpo [review_platform: Yotpo].

## Opportunities
1. Paid returns [free_returns: no].
2. No loyalty program, which leaves room for"""


def _facts():
    return ai_analyzer.build_prompt(DATA, "en")[2]


# --- prompt ---------------------------------------------------------------------------------

def test_prompt_lists_only_known_pipeline_fields():
    system, user, facts = ai_analyzer.build_prompt(DATA, "en")
    assert set(facts) <= set(ai_analyzer.PROMPT_FIELDS)
    # unknown values are left out, not written as N/A
    for unknown in ("has_popup", "has_referral", "review_count", "announcement_bar"):
        assert unknown not in facts
    assert "N/A" not in user and "None" not in user
    assert facts["free_shipping_threshold"] == "$100" and facts["return_days"] == "30"
    assert facts["free_returns"] == "no" and facts["has_email_capture"] == "yes"
    assert facts["products_sampled"] == "50 products from 5 collections"
    for name, value in facts.items():
        assert f"- {name}: {value}" in user


def test_prompt_asks_for_the_three_sections_with_citations():
    system, user, _ = ai_analyzer.build_prompt(DATA, "en")
    for heading in ("## Positioning", "## Risks", "## Opportunities"):
        assert heading in user
    assert "[field: value]" in user and "three" in user.lower()
    assert "English" in system


def test_prompt_follows_the_report_language_and_keeps_english_headings():
    system, user, facts = ai_analyzer.build_prompt(DATA, "zh")
    assert "中文" in system or "Chinese" in system
    assert "## Risks" in user and facts == _facts()


# --- parser ---------------------------------------------------------------------------------

def test_parser_clean_response():
    out = ai_analyzer.parse_analysis(CLEAN, _facts())
    assert out["positioning"].startswith("A premium natural-materials shoe brand")
    assert len(out["risks"]) == 3 and len(out["opportunities"]) == 3
    assert out["risks"][0].endswith("[free_shipping_threshold: $100].")
    assert out["opportunities"][2] == "Entry products start at $14 [price_min: $14]."


def test_parser_ignores_prose_around_the_sections():
    out = ai_analyzer.parse_analysis(EXTRA_PROSE, _facts())
    assert "Sure!" not in out["positioning"] and "hope" not in out["positioning"]
    assert out["opportunities"] == ["Paid returns [free_returns: no]", "No loyalty program [has_loyalty: no]",
                                    "Low entry price [price_min: $14]"]
    assert all("Let me know" not in item for item in out["opportunities"])


def test_parser_rejects_a_truncated_response():
    with pytest.raises(ai_analyzer.AIError) as err:
        ai_analyzer.parse_analysis(TRUNCATED, _facts())
    assert err.value.error_type == "parse"


@pytest.mark.parametrize("bad", [
    CLEAN.replace("[price_min: $14]", ""),                       # an item with no citation
    CLEAN.replace("[price_min: $14]", "[total_revenue: $1M]"),   # cites a field the prompt did not list
    CLEAN.replace("## Positioning", "## Summary"),               # a section missing
    CLEAN.replace("3. Yotpo reviews build trust [review_platform: Yotpo].\n",
                  "3. Yotpo reviews [review_platform: Yotpo].\n4. More [price_max: $145].\n"),  # four risks
    "",
])
def test_parser_rejects_responses_that_do_not_fit(bad):
    with pytest.raises(ai_analyzer.AIError) as err:
        ai_analyzer.parse_analysis(bad, _facts())
    assert err.value.error_type == "parse"


# --- analyzer: one call, parse failures logged ------------------------------------------------

class FakeProvider:
    name, model = "deepseek", "deepseek-flash"

    def __init__(self, text, finish_reason="stop"):
        self.text, self.finish_reason, self.calls = text, finish_reason, []

    def is_available(self):
        return True

    def chat(self, system, user):
        self.calls.append((system, user))
        return ai_analyzer.ChatResult(self.text, prompt_tokens=400, completion_tokens=200,
                                      finish_reason=self.finish_reason)


@pytest.fixture
def run_log(tmp_path):
    obs.init_run(log_dir=str(tmp_path), run_id="p")
    path = tmp_path / "run_p.jsonl"
    yield lambda: [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    obs.close_run()


def _calls(events):
    return [e for e in events if e["context"].get("kind") == "ai_call"]


def test_analyzer_makes_one_call_and_returns_the_sections(run_log):
    provider = FakeProvider(CLEAN)
    out = ai_analyzer.AIAnalyzer(provider=provider, language="en").analyze_site(DATA)
    assert len(provider.calls) == 1
    assert (out["provider"], out["model"]) == ("deepseek", "deepseek-flash")
    assert len(out["risks"]) == 3 and "error" not in out
    (e,) = _calls(run_log())
    assert e["event"] == "success" and e["context"]["prompt_tokens"] == 400


@pytest.mark.parametrize("text,finish", [(TRUNCATED, "stop"), (CLEAN, "length")])
def test_a_response_that_does_not_fit_is_logged_as_parse(run_log, text, finish):
    out = ai_analyzer.AIAnalyzer(provider=FakeProvider(text, finish), language="en").analyze_site(DATA)
    assert out == {"provider": "deepseek", "model": "deepseek-flash", "error": "parse"}
    (e,) = _calls(run_log())
    assert (e["event"], e["error_type"]) == ("fail", "parse")
    assert (e["context"]["prompt_tokens"], e["context"]["completion_tokens"]) == (400, 200)


# --- reports --------------------------------------------------------------------------------

def _intel(ai=None):
    intel = SiteIntelligence(domain="example.com", url="https://example.com", scan_timestamp=datetime(2026, 10, 12),
                             platform=Platform.SHOPIFY, price_min=14.0, price_max=145.0, price_median=105.0,
                             shipping_policy=ShippingPolicy(free_shipping_threshold=100.0),
                             return_policy=ReturnPolicy(return_days=30, free_returns=False))
    intel.pages_crawled = ["https://example.com"]
    if ai is not None:
        intel.ai_analysis = ai
    return intel


def _reports(tmp_path, intel, lang="en", **run):
    from modules.business_report import BusinessReportGenerator
    from modules.report_writer import ReportWriter
    md, _ = ReportWriter(str(tmp_path), language=lang).write_full_report([intel], {}, "report")
    run_info = dict({"ignore_robots": False, "render_js": False, "ai_requested": True, "ai_available": True,
                     "ai_provider": "deepseek", "ai_model": "deepseek-flash"}, **run)
    biz = BusinessReportGenerator(str(tmp_path), language=lang).generate_report(
        [intel], {}, {}, "business_report", run_info=run_info)
    return Path(md).read_text(encoding="utf-8"), Path(biz).read_text(encoding="utf-8")


PARSED = dict(ai_analyzer.parse_analysis(CLEAN, _facts()), provider="deepseek", model="deepseek-flash")


@pytest.mark.parametrize("lang", ["en", "zh"])
def test_both_reports_label_the_ai_section_with_provider_and_model(tmp_path, lang):
    md, biz = _reports(tmp_path, _intel(PARSED), lang)
    for text in (md, biz):
        assert "deepseek / deepseek-flash" in text
        assert "[free_shipping_threshold: $100]" in text and "Entry products start at $14" in text
    # the rule-based insights are still there; the AI section is added, not swapped in
    assert ("Key Insights" if lang == "en" else "关键洞察") in md


def test_methodology_says_the_scan_text_was_sent_to_the_provider(tmp_path):
    _, biz = _reports(tmp_path, _intel(PARSED))
    method = biz.split("### Methodology", 1)[1]
    assert "sent to DeepSeek" in method and "deepseek-flash" in method
    _, biz = _reports(tmp_path, _intel(dict(PARSED, provider="ollama", model="qwen2.5:7b")),
                      ai_provider="ollama", ai_model="qwen2.5:7b")
    method = biz.split("### Methodology", 1)[1]
    assert "local Ollama model" in method and "did not leave this machine" in method


@pytest.mark.parametrize("lang,word", [("en", "AI analysis unavailable"), ("zh", "AI 分析不可用")])
def test_a_failed_analysis_says_unavailable_and_prints_no_text(tmp_path, lang, word):
    md, biz = _reports(tmp_path, _intel({"provider": "deepseek", "model": "deepseek-flash", "error": "parse"}), lang)
    for text in (md, biz):
        assert word in text and "deepseek / deepseek-flash" in text
        assert "## Risks" not in text


def test_no_ai_section_without_the_step(tmp_path):
    md, biz = _reports(tmp_path, _intel(), ai_requested=False, ai_available=False)
    assert "deepseek" not in md and "AI analysis" not in md
    assert "LLM step was not run" in biz
