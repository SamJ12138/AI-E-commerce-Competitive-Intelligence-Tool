"""scripts/real_corpus.py scoring rules (offline: no store is contacted)."""

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import real_corpus  # noqa: E402


@pytest.mark.parametrize("exp, got, kind, accept, verdict", [
    (75.0, 75.0, "number", None, "match"),
    (75.0, None, "number", None, "missing"),
    (75.0, 50.0, "number", None, "mismatch"),
    (60, 30.0, "number", [60, 30], "match"),
    (None, None, "number", None, "match"),
    (None, 50.0, "number", None, "mismatch"),
    (False, None, "bool", None, "missing"),
    (None, False, "bool", None, "mismatch"),
    ("Shopify", "Custom/Unknown", "text", None, "missing"),
    ("Custom/Unknown", "Custom/Unknown", "text", None, "match"),
    (["PayPal", "Shop Pay"], ["PayPal"], "set", None, "partial"),
    ([], [], "set", None, "match"),
    ([], ["Visa"], "set", None, "mismatch"),
])
def test_field_verdicts(exp, got, kind, accept, verdict):
    assert real_corpus.verdict_value(exp, got, kind, accept)[0] == verdict


def _p(url, price, compare=None):
    return {"url": url, "price": {"current_price": price, "compare_at_price": compare}}


def test_products_by_url_path_with_range_and_compare_at():
    expected = [
        {"title": "a", "url": "https://s.test/products/a", "price": 4.99, "compare_at": 19.99},
        {"title": "b", "url": "https://s.test/products/b/", "price": 129.0, "compare_at": None, "price_range": [129.0, 149.0]},
        {"title": "c", "url": "https://s.test/products/c", "price": 10.0, "compare_at": None},
    ]
    tool = [_p("https://www.s.test/products/a?variant=1", 4.99, 19.99), _p("https://s.test/products/b", 149.0),
            _p("https://s.test/products/c", 12.0)]
    overall, note, rows = real_corpus.score_products(expected, tool)
    assert [r["verdict"] for r in rows] == ["match", "match", "mismatch"]
    assert overall == "partial"
    assert real_corpus.score_products(expected, [])[0] == "missing"
    assert real_corpus.score_products([], [])[0] == "match"
    assert real_corpus.score_products([], tool)[0] == "mismatch"


def test_ground_truth_files_are_complete_and_hold_no_page_html():
    truth = real_corpus.load_truth()
    assert len(truth) == 8
    for store, data in truth.items():
        assert set(real_corpus.ORDER[1:]) <= set(data["fields"]), store
        for name, spec in data["fields"].items():
            assert spec["source"].startswith("http") or spec["source"] == "product pages", (store, name)
            text = json.dumps(spec).lower()
            assert "<html" not in text and "<body" not in text, (store, name)
        if data["fields"]["products"]["value"]:
            assert 3 <= len(data["fields"]["products"]["value"]) <= 5, store
    assert {d["status"] for d in truth.values()} == {"ok", "blocked"}
