"""B1: the synthetic pricing model is gone; the old "ML" threat score is a rule-based
competitive pressure score whose weights, factor scores and inputs are printed."""

import ast
import re
from datetime import datetime
from pathlib import Path

import pytest

from modules.models import Platform, SiteIntelligence, ShippingPolicy

REPO = Path(__file__).resolve().parent.parent


def _intel(**kw):
    base = dict(domain="example.com", url="https://example.com", scan_timestamp=datetime(2026, 10, 11),
                platform=Platform.SHOPIFY, price_min=24.0, price_max=39.0, price_median=31.5,
                has_email_capture=True, review_platform="Yotpo", payment_methods=["PayPal", "Visa"],
                categories=["Tees", "Hoodies"])
    base.update(kw)
    return SiteIntelligence(**base)


def _report(tmp_path, intel, lang="en"):
    from modules.report_writer import ReportWriter
    md, _ = ReportWriter(str(tmp_path), language=lang).write_full_report([intel], {}, "report")
    return Path(md).read_text(encoding="utf-8")


def test_weights_sum_to_one_and_score_is_the_rounded_weighted_sum():
    from modules.pressure_score import WEIGHTS, score_pressure
    assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9
    result = score_pressure(_intel())
    total = sum(f["weight"] * f["score"] for f in result["factors"])
    assert result["weighted_sum"] == pytest.approx(round(total, 2))
    assert result["score"] == max(1, min(10, round(total)))
    assert {f["key"] for f in result["factors"]} == set(WEIGHTS)


def test_shipping_factor_reads_the_nested_shipping_policy():
    """The old ThreatScorer read a top-level key to_dict() never has, so this factor was always 5."""
    from modules.pressure_score import score_pressure
    free_all = score_pressure(_intel(shipping_policy=ShippingPolicy(free_shipping_threshold=0)))
    over_30 = score_pressure(_intel(shipping_policy=ShippingPolicy(free_shipping_threshold=30)))
    unknown = score_pressure(_intel())
    ship = lambda r: next(f for f in r["factors"] if f["key"] == "shipping_advantage")
    assert (ship(free_all)["score"], ship(over_30)["score"], ship(unknown)["score"]) == (9, 7, 5)
    assert ship(over_30)["inputs"] == {"free_shipping_threshold": 30}


def test_unknown_price_is_neutral_and_shown_as_unknown():
    from modules.pressure_score import score_pressure
    r = score_pressure(_intel(price_min=None, price_max=None, price_median=None))
    price = next(f for f in r["factors"] if f["key"] == "price_competitiveness")
    assert price["score"] == 5 and price["inputs"] == {"price_median": None}


def test_report_prints_pressure_score_with_weights_and_no_threat_or_pricing(tmp_path):
    from modules.pressure_score import WEIGHTS, score_pressure
    md = _report(tmp_path, _intel())
    assert "Competitive pressure score (rule-based)" in md
    section = md.split("Competitive pressure score (rule-based)", 1)[1].split("\n### ", 1)[0]
    for w in WEIGHTS.values():
        assert f"{w:.2f}" in section
    assert f"**{score_pressure(_intel())['score']}/10**" in section
    for gone in ("Threat", "threat", "Pricing Strategy", "Suggested", "Competitor Median"):
        assert gone not in md


def test_zh_report_labels_pressure_score_as_rule_based(tmp_path):
    md = _report(tmp_path, _intel(), lang="zh")
    assert "竞争压力评分（规则计算）" in md
    assert "威胁" not in md and "建议最优价" not in md


def test_no_synthetic_model_code_left():
    import modules.ai_analyzer as ai
    for name in ("PricingPredictor", "ThreatScorer", "SKLEARN_AVAILABLE", "XGBOOST_AVAILABLE"):
        assert not hasattr(ai, name), name
    cfg = ai.AIConfig()
    for key in ("enable_pricing_prediction", "enable_threat_scoring", "pricing_model_path", "threat_model_path"):
        assert not hasattr(cfg, key), key


@pytest.mark.parametrize("path", [REPO / "main.py"] + sorted((REPO / "modules").glob("*.py")),
                         ids=lambda p: p.name)
def test_no_ml_or_unused_imports(path):
    banned = {"numpy", "sklearn", "xgboost", "pickle", "deepdiff", "pandas"}
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module.split(".")[0])
    assert not (found & banned), f"{path.name} imports {sorted(found & banned)}"


def test_ai_wording_only_in_the_llm_step():
    """No 'ML', 'machine learning', 'XGBoost' or 'classifier' claims left in code or requirements."""
    pattern = re.compile(r"\bML\b|machine learning|xgboost|scikit|classifier", re.I)
    offenders = []
    for path in [REPO / "main.py", REPO / "requirements.txt", REPO / "README.md"] + sorted((REPO / "modules").glob("*.py")):
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if pattern.search(line):
                offenders.append(f"{path.name}:{i}: {line.strip()[:80]}")
    assert not offenders, "\n".join(offenders)
