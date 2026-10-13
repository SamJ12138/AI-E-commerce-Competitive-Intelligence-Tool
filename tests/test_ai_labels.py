"""B1: only the Ollama step is called AI, and only when it produced the text shown."""

import re
from datetime import datetime
from pathlib import Path

from modules.models import Platform, SiteIntelligence

AI_WORD = re.compile(r"\bAI\b|Qwen|Ollama|人工智能|大模型")
LLM_INSIGHTS = {"key_insights": ["LLM insight one", "LLM insight two"],
                "recommendations": ["LLM rec"], "raw_response": "## 关键洞察\n- LLM insight one"}
TEMPLATE_INSIGHTS = {"key_insights": ["【平台】使用Shopify平台"], "recommendations": ["建议启用Ollama获取AI智能分析"],
                     "ai_powered": False}


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


def test_template_fallback_is_not_labelled_ai(tmp_path):
    intel = _intel()
    intel.ai_insights = TEMPLATE_INSIGHTS
    intel.ai_positioning = "AI分析不可用"
    md, biz = _reports(tmp_path, intel)
    assert not AI_WORD.search(md) and not AI_WORD.search(biz)
    assert "建议启用Ollama" not in md


def test_llm_output_is_labelled_with_the_model(tmp_path):
    intel = _intel()
    intel.ai_insights = LLM_INSIGHTS
    intel.ai_positioning = "LLM positioning text"
    intel.ai_model = "qwen2.5:7b"
    md, biz = _reports(tmp_path, intel)
    assert "LLM insight one" in md and "LLM positioning text" in md
    assert "Ollama" in md and "qwen2.5:7b" in md
    assert "Ollama" in biz and "qwen2.5:7b" in biz


def test_analyzer_returns_llm_output_only_and_no_pricing_or_threat(monkeypatch):
    from modules import ai_analyzer
    monkeypatch.setattr(ai_analyzer.OllamaProvider, "is_available", lambda self: True)
    monkeypatch.setattr(ai_analyzer.LLMClient, "generate",
                        lambda self, prompt, system=None: "## 关键洞察\n- one\n- two\n## 可复制的动作建议\n- act")
    results = ai_analyzer.AIAnalyzer(ai_analyzer.AIConfig(provider="ollama", model="m:1")).analyze_site(_intel().to_dict())
    assert results["insights_from_llm"] and results["positioning_from_llm"]
    assert results["insights"]["key_insights"] == ["one", "two"]
    assert "pricing" not in results and "threat" not in results
