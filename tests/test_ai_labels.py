"""B1: only the LLM step is called AI, and only when it ran; its section names provider and model."""

import re
from datetime import datetime
from pathlib import Path

from modules.models import Platform, SiteIntelligence

AI_WORD = re.compile(r"\bAI\b|Qwen|Ollama|ollama|DeepSeek|deepseek|人工智能|大模型")
ANALYSIS = {"provider": "ollama", "model": "qwen2.5:7b", "positioning": "LLM positioning [platform: Shopify]",
            "risks": ["r1 [price_min: $24]", "r2 [price_max: $39]", "r3 [platform: Shopify]"],
            "opportunities": ["o1 [price_min: $24]", "o2 [price_max: $39]", "o3 [platform: Shopify]"]}


def _intel(**kw):
    return SiteIntelligence(domain="example.com", url="https://example.com", scan_timestamp=datetime(2026, 10, 11),
                            platform=Platform.SHOPIFY, price_min=24.0, price_max=39.0, price_median=31.5, **kw)


def _reports(tmp_path, intel, lang="en"):
    from modules.business_report import BusinessReportGenerator
    from modules.report_writer import ReportWriter
    md, _ = ReportWriter(str(tmp_path), language=lang).write_full_report([intel], {}, "report")
    biz = BusinessReportGenerator(str(tmp_path), language=lang).generate_report([intel], {}, {}, "business_report")
    return Path(md).read_text(encoding="utf-8"), Path(biz).read_text(encoding="utf-8")


def test_no_ai_wording_without_the_llm(tmp_path):
    md, biz = _reports(tmp_path, _intel())
    assert not AI_WORD.search(md), AI_WORD.search(md).group(0)
    assert not AI_WORD.search(biz), AI_WORD.search(biz).group(0)


def test_llm_output_is_labelled_with_provider_and_model(tmp_path):
    md, biz = _reports(tmp_path, _intel(ai_analysis=ANALYSIS))
    for text in (md, biz):
        assert "LLM positioning [platform: Shopify]" in text and "o3 [platform: Shopify]" in text
        assert "AI analysis (ollama / qwen2.5:7b)" in text
    assert "Ollama, model qwen2.5:7b" in biz


def test_analyzer_returns_the_three_sections_and_no_pricing_or_threat():
    from modules import ai_analyzer

    class Provider:
        name, model = "ollama", "m:1"

        def is_available(self):
            return True

        def chat(self, system, user):
            return ai_analyzer.ChatResult("## Positioning\np [platform: Shopify]\n## Risks\n1. a [platform: Shopify]\n"
                                          "2. b [platform: Shopify]\n3. c [platform: Shopify]\n## Opportunities\n"
                                          "1. d [platform: Shopify]\n2. e [platform: Shopify]\n3. f [platform: Shopify]")

    results = ai_analyzer.AIAnalyzer(provider=Provider()).analyze_site(_intel().to_dict())
    assert set(results) == {"provider", "model", "positioning", "risks", "opportunities"}
    assert results["risks"] == ["a [platform: Shopify]", "b [platform: Shopify]", "c [platform: Shopify]"]
